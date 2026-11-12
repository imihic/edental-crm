from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compliance import AuditAction, record_audit
from app.identity import Role, current_staff, login_required, require_role
from app.people.events import RecordsMerged
from app.people.models import Consent, Enquiry, Lead, Patient
from app.people.patient_service import detail_of, is_oib_conflict, validation_failed
from app.people.schemas import ConflictResponse, PatientDetail, PatientPath
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse
from app.platform.events import publish

api = APIBlueprint("merge", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES)

PATIENT_FIELDS = {
    "first_name": "first_name",
    "last_name": "last_name",
    "date_of_birth": "date_of_birth",
    "phone": "phone_e164",
    "email": "email",
    "oib": "oib",
    "address": "address",
    "notes": "notes",
    "preferred_clinic_id": "preferred_clinic_id",
    "preferred_language": "preferred_language",
}
LEAD_FIELDS = {"phone": "phone_e164", "email": "email"}


class MergeIn(BaseModel):
    retired_kind: Literal["patient", "lead"]
    retired_id: UUID
    field_choices: dict[str, Literal["kept", "retired"]] = {}


_MOVE_AS_CHILD = text(
    """
    WITH moved AS (
        DELETE FROM guardian_links g
        WHERE g.patient_id = :retired
          AND g.ended_at IS NULL
          AND g.guardian_patient_id IS DISTINCT FROM :kept
          AND NOT EXISTS (
              SELECT 1 FROM guardian_links e
              WHERE e.patient_id = :kept
                AND e.ended_at IS NULL
                AND (e.guardian_patient_id = g.guardian_patient_id OR e.guardian_contact_id = g.guardian_contact_id)
          )
        RETURNING g.*
    )
    INSERT INTO guardian_links
        (id, organization_id, patient_id, guardian_patient_id, guardian_contact_id, relationship, created_at)
    SELECT id, organization_id, :kept, guardian_patient_id, guardian_contact_id, relationship, created_at FROM moved
    """
)
_MOVE_AS_GUARDIAN = text(
    """
    WITH moved AS (
        DELETE FROM guardian_links g
        WHERE g.guardian_patient_id = :retired
          AND g.ended_at IS NULL
          AND g.patient_id <> :kept
          AND NOT EXISTS (
              SELECT 1 FROM guardian_links e
              WHERE e.patient_id = g.patient_id AND e.guardian_patient_id = :kept AND e.ended_at IS NULL
          )
        RETURNING g.*
    )
    INSERT INTO guardian_links
        (id, organization_id, patient_id, guardian_patient_id, guardian_contact_id, relationship, created_at)
    SELECT id, organization_id, patient_id, :kept, guardian_contact_id, relationship, created_at FROM moved
    """
)


def _lock(db: Session, kept_id: UUID, body: MergeIn) -> tuple[Patient, Patient | Lead]:
    patient_ids = {kept_id} | ({body.retired_id} if body.retired_kind == "patient" else set())
    patients = {
        p.id: p
        for p in db.scalars(
            select(Patient)
            .where(Patient.id.in_(patient_ids))
            .order_by(Patient.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    if body.retired_kind == "patient":
        retired = patients.get(body.retired_id)
    else:
        retired = db.scalars(
            select(Lead).where(Lead.id == body.retired_id).with_for_update().execution_options(populate_existing=True)
        ).one_or_none()
    kept = patients.get(kept_id)
    if kept is None or retired is None:
        raise ApiError(404, "not_found")
    return kept, retired


def _copy_consents(db: Session, staff, kept: Patient, retired: Patient | Lead) -> None:
    subject = Consent.patient_id if isinstance(retired, Patient) else Consent.lead_id
    for entry in db.scalars(select(Consent).where(subject == retired.id).order_by(Consent.recorded_at, Consent.id)):
        db.add(
            Consent(
                organization_id=staff.organization_id,
                patient_id=kept.id,
                purpose=entry.purpose,
                granted=entry.granted,
                source="merge",
                carried_from_consent_id=entry.id,
                recorded_by_staff_member_id=staff.id,
                recorded_at=entry.recorded_at,
            )
        )


@api.post(
    "/api/patients/<uuid:patient_id>/merge",
    responses={
        200: PatientDetail,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ConflictResponse,
    },
)
@login_required
@require_role(Role.RECEPTIONIST, Role.CLINIC_MANAGER)
def merge_records(path: PatientPath, body: MergeIn):
    """Merge a duplicate Patient or Lead into this Patient. Cannot be undone.

    Staff pick, per field, the kept or the retired record's value; Enquiries, Consents (copied) and guardian links
    move to this Patient and the other record is retired, not deleted.
    """
    db = get_session()
    staff = current_staff()
    allowed = PATIENT_FIELDS if body.retired_kind == "patient" else LEAD_FIELDS
    if any(field not in allowed for field in body.field_choices):
        return validation_failed(["field_choices"])
    if body.retired_kind == "patient" and body.retired_id == path.patient_id:
        raise ApiError(409, "invalid_merge")
    kept, retired = _lock(db, path.patient_id, body)
    if kept.retired_at is not None or retired.retired_at is not None:
        raise ApiError(409, "invalid_merge")

    taken = {allowed[f]: getattr(retired, allowed[f]) for f, c in body.field_choices.items() if c == "retired"}
    try:
        with db.begin_nested():
            if "oib" in taken:
                retired.oib = None
                db.flush()
            for column, value in taken.items():
                setattr(kept, column, value)
            db.flush()
    except IntegrityError as exc:
        if not is_oib_conflict(exc):
            raise
        raise ApiError(409, "oib_taken") from exc

    owner = Enquiry.patient_id if isinstance(retired, Patient) else Enquiry.lead_id
    db.execute(update(Enquiry).where(owner == retired.id).values(patient_id=kept.id))
    _copy_consents(db, staff, kept, retired)
    if isinstance(retired, Patient):
        ids = {"retired": retired.id, "kept": kept.id}
        db.execute(_MOVE_AS_CHILD, ids)
        db.execute(_MOVE_AS_GUARDIAN, ids)
    retired.retired_into_patient_id = kept.id
    retired.retired_at = datetime.now(UTC)
    db.flush()

    common = {"organization_id": staff.organization_id, "staff_member_id": staff.id, "account_id": staff.account_id}
    record_audit(
        db,
        action=AuditAction.UPDATE,
        entity_type="patient",
        entity_id=kept.id,
        detail={"fields": sorted(body.field_choices) + ["merged"]},
        **common,
    )
    record_audit(
        db,
        action=AuditAction.DELETE,
        entity_type=body.retired_kind,
        entity_id=retired.id,
        detail={"merged_into": str(kept.id)},
        **common,
    )
    publish(
        db,
        RecordsMerged(
            organization_id=staff.organization_id,
            kept_patient_id=kept.id,
            retired_kind=body.retired_kind,
            retired_id=retired.id,
        ),
    )
    db.refresh(kept)
    return detail_of(db, kept)
