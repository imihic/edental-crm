from datetime import UTC, datetime

from flask import Response
from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.guardian_service import guardian_out
from app.people.models import Contact, GuardianLink, Patient
from app.people.patient_service import clean_fields, load_patient, merged_response, validation_failed
from app.people.schemas import GuardianIn, GuardianOut, GuardianPath, MergedResponse, PatientPath
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response

api = APIBlueprint("guardians", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES)

GUARDIAN_UNIQUE_CONSTRAINT = "uq_guardian_links_patient_guardian"


def _audit_guardians_changed(db, staff, patient: Patient) -> None:
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.UPDATE,
        entity_type="patient",
        entity_id=patient.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
        detail={"fields": ["guardians"]},
    )


@api.post(
    "/api/patients/<uuid:patient_id>/guardians",
    responses={
        201: GuardianOut,
        401: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        410: MergedResponse,
    },
)
@login_required
def add_guardian(path: PatientPath, body: GuardianIn):
    """Link a Guardian: an existing Patient or a new Contact. Audited as an update of the Patient."""
    db = get_session()
    staff = current_staff()
    patient = load_patient(db, path.patient_id)
    if patient.retired_at is not None:
        return merged_response(patient)
    if (body.guardian_patient_id is None) == (body.contact is None):
        return validation_failed(["guardian_patient_id", "contact"])
    guardian_patient = contact = None
    if body.guardian_patient_id is not None:
        if body.guardian_patient_id == patient.id:
            return validation_failed(["guardian_patient_id"])
        guardian_patient = load_patient(db, body.guardian_patient_id)
        if guardian_patient.retired_at is not None:
            return merged_response(guardian_patient)
        link = GuardianLink(
            organization_id=staff.organization_id,
            patient_id=patient.id,
            guardian_patient_id=guardian_patient.id,
            relationship=body.relationship,
        )
    else:
        clean, bad = clean_fields(db, {"phone": body.contact.phone})
        if bad:
            return validation_failed(["contact.phone"])
        contact = Contact(
            organization_id=staff.organization_id,
            full_name=body.contact.full_name,
            phone_e164=clean["phone_e164"],
            email=(body.contact.email or None),
        )
        db.add(contact)
        db.flush()
        link = GuardianLink(
            organization_id=staff.organization_id,
            patient_id=patient.id,
            guardian_contact_id=contact.id,
            relationship=body.relationship,
        )
    try:
        with db.begin_nested():
            db.add(link)
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) != GUARDIAN_UNIQUE_CONSTRAINT:
            raise
        return error_response(409, "guardian_exists")
    db.refresh(link)
    _audit_guardians_changed(db, staff, patient)
    return guardian_out(link, guardian_patient, contact).model_dump(mode="json"), 201


@api.delete(
    "/api/patients/<uuid:patient_id>/guardians/<uuid:link_id>",
    responses={204: None, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse},
)
@login_required
def remove_guardian(path: GuardianPath):
    """Unlink a Guardian (a Contact row stays). Audited as an update of the Patient."""
    db = get_session()
    staff = current_staff()
    patient = load_patient(db, path.patient_id, for_key_share=True)
    if patient.retired_at is not None:
        return merged_response(patient)
    link = db.scalar(
        select(GuardianLink)
        .where(GuardianLink.id == path.link_id, GuardianLink.patient_id == patient.id, GuardianLink.ended_at.is_(None))
        .with_for_update()
    )
    if link is None:
        raise ApiError(404, "not_found")
    link.ended_at = datetime.now(UTC)
    db.flush()
    _audit_guardians_changed(db, staff, patient)
    return Response(status=204)
