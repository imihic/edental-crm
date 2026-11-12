from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy.exc import IntegrityError

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.patient_service import (
    clean_fields,
    detail_of,
    is_oib_conflict,
    load_patient,
    merged_response,
    oib_taken,
    validation_failed,
)
from app.people.schemas import EDITABLE_FIELDS, ConflictResponse, MergedResponse, PatientDetail, PatientPatch, PatientPath
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse, error_response

api = APIBlueprint(
    "patient_update", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES
)


@api.patch(
    "/api/patients/<uuid:patient_id>",
    responses={
        200: PatientDetail,
        401: ErrorResponse,
        404: ErrorResponse,
        409: ConflictResponse,
        410: MergedResponse,
    },
)
@login_required
def update_patient(path: PatientPath, body: PatientPatch):
    """Change the sent fields. The audit entry lists changed field names only."""
    db = get_session()
    staff = current_staff()
    patient = load_patient(db, path.patient_id, for_update=True)
    if patient.retired_at is not None:
        return merged_response(patient)
    clean, bad = clean_fields(db, body.model_dump(exclude_unset=True))
    if bad:
        return validation_failed(bad)
    changed = []
    for name in EDITABLE_FIELDS:
        column = "phone_e164" if name == "phone" else name
        if column in clean and clean[column] != getattr(patient, column):
            changed.append(name)
    if "oib" in changed and clean["oib"] and oib_taken(db, clean["oib"], except_id=patient.id):
        return error_response(409, "oib_taken")
    if changed:
        try:
            with db.begin_nested():
                for name in changed:
                    column = "phone_e164" if name == "phone" else name
                    setattr(patient, column, clean[column])
        except IntegrityError as exc:
            if not is_oib_conflict(exc):
                raise
            return error_response(409, "oib_taken")
        db.refresh(patient)
        record_audit(
            db,
            organization_id=staff.organization_id,
            action=AuditAction.UPDATE,
            entity_type="patient",
            entity_id=patient.id,
            staff_member_id=staff.id,
            account_id=staff.account_id,
            detail={"fields": changed},
        )
    return detail_of(db, patient)
