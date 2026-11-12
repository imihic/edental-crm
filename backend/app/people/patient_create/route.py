from flask_openapi3 import APIBlueprint, Tag

from app.identity import current_staff, login_required
from app.people.patient_service import create_patient_record, detail_of
from app.people.schemas import ConflictResponse, PatientCreate, PatientDetail
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "patient_create", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES
)


@api.post("/api/patients", responses={201: PatientDetail, 401: ErrorResponse, 409: ConflictResponse})
@login_required
def create_patient(body: PatientCreate):
    """Create a Patient; possible duplicates are a 409 warning unless `confirm_duplicates` is set."""
    db = get_session()
    patient, failure = create_patient_record(db, current_staff(), body)
    if failure is not None:
        return failure
    return detail_of(db, patient), 201
