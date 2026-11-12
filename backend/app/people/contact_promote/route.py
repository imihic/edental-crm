from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import text

from app.identity import current_staff, login_required
from app.people.models import Contact
from app.people.patient_service import create_patient_record, detail_of
from app.people.schemas import ConflictResponse, ContactPath, PatientCreate, PatientDetail
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse

api = APIBlueprint(
    "contact_promote", __name__, abp_tags=[Tag(name="contacts")], abp_responses=VALIDATION_ERROR_RESPONSES
)

_MOVE_ACTIVE_LINKS = text(
    """
    WITH moved AS (
        DELETE FROM guardian_links WHERE guardian_contact_id = :contact AND ended_at IS NULL
        RETURNING id, organization_id, patient_id, relationship, created_at
    )
    INSERT INTO guardian_links (id, organization_id, patient_id, guardian_patient_id, relationship, created_at)
    SELECT id, organization_id, patient_id, :patient, relationship, created_at FROM moved
    """
)


@api.post(
    "/api/contacts/<uuid:contact_id>/promote",
    responses={201: PatientDetail, 401: ErrorResponse, 404: ErrorResponse, 409: ConflictResponse},
)
@login_required
def promote_contact(path: ContactPath, body: PatientCreate):
    """Make a Contact a Patient: creates the Patient and repoints the Contact's guardian links to it."""
    db = get_session()
    staff = current_staff()
    contact = db.get(Contact, path.contact_id, with_for_update=True)
    if contact is None:
        raise ApiError(404, "not_found")
    if contact.promoted_to_patient_id is not None:
        raise ApiError(409, "contact_already_promoted")
    patient, failure = create_patient_record(db, staff, body)
    if failure is not None:
        return failure
    db.execute(_MOVE_ACTIVE_LINKS, {"contact": contact.id, "patient": patient.id})
    contact.promoted_to_patient_id = patient.id
    db.flush()
    return detail_of(db, patient), 201
