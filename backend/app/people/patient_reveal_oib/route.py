from flask_openapi3 import APIBlueprint, Tag

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.patient_service import load_patient, merged_response
from app.people.schemas import MergedResponse, PatientPath, RevealOibResponse
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "patient_reveal_oib", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES
)


@api.post(
    "/api/patients/<uuid:patient_id>/reveal-oib",
    responses={200: RevealOibResponse, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse},
)
@login_required
def reveal_oib(path: PatientPath):
    """The Patient's full OIB. Audited as `view` of the `oib` field (the value is never logged)."""
    db = get_session()
    staff = current_staff()
    patient = load_patient(db, path.patient_id)
    if patient.retired_at is not None:
        return merged_response(patient)
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.VIEW,
        entity_type="patient",
        entity_id=patient.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
        detail={"field": "oib"},
    )
    return {"oib": patient.oib}
