from flask_openapi3 import APIBlueprint, Tag

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.patient_service import detail_of, load_patient, merged_response
from app.people.schemas import MergedResponse, PatientDetail, PatientPath
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "patient_detail", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES
)


@api.get(
    "/api/patients/<uuid:patient_id>",
    responses={200: PatientDetail, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse},
)
@login_required
def get_patient(path: PatientPath):
    """A Patient's full record (OIB masked). Every read is audited as `view`."""
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
    )
    return detail_of(db, patient)
