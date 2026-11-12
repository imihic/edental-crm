from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import select, update

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.events import LeadConverted
from app.people.lead_service import merged_lead_response
from app.people.models import Consent, Enquiry, Lead
from app.people.patient_service import create_patient_record, detail_of
from app.people.schemas import ConflictResponse, LeadPath, MergedResponse, PatientCreate, PatientDetail
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response
from app.platform.events import publish

api = APIBlueprint("lead_convert", __name__, abp_tags=[Tag(name="leads")], abp_responses=VALIDATION_ERROR_RESPONSES)


@api.post(
    "/api/leads/<uuid:lead_id>/convert",
    responses={
        201: PatientDetail,
        401: ErrorResponse,
        404: ErrorResponse,
        409: ConflictResponse,
        410: MergedResponse,
    },
)
@login_required
def convert_lead(path: LeadPath, body: PatientCreate):
    """Convert a Lead into a new Patient: carries its Enquiries and Consents over and marks the Lead converted."""
    db = get_session()
    staff = current_staff()
    lead = db.scalars(
        select(Lead).where(Lead.id == path.lead_id).with_for_update().execution_options(populate_existing=True)
    ).one_or_none()
    if lead is None:
        raise ApiError(404, "not_found")
    if lead.retired_at is not None:
        return merged_lead_response(lead)
    if lead.stage == "converted":
        return error_response(409, "invalid_transition")
    patient, failure = create_patient_record(db, staff, body, exclude_lead_id=lead.id)
    if failure is not None:
        return failure

    lead.stage = "converted"
    lead.lost_reason = None
    lead.lost_note = None
    lead.converted_patient_id = patient.id
    db.flush()
    db.execute(update(Enquiry).where(Enquiry.lead_id == lead.id).values(patient_id=patient.id))
    entries = db.scalars(select(Consent).where(Consent.lead_id == lead.id).order_by(Consent.recorded_at, Consent.id)).all()
    for entry in entries:
        db.add(
            Consent(
                organization_id=staff.organization_id,
                patient_id=patient.id,
                purpose=entry.purpose,
                granted=entry.granted,
                source="conversion",
                carried_from_consent_id=entry.id,
                recorded_by_staff_member_id=staff.id,
                recorded_at=entry.recorded_at,
            )
        )
    db.flush()
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.UPDATE,
        entity_type="lead",
        entity_id=lead.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
        detail={"fields": ["stage"]},
    )
    publish(db, LeadConverted(organization_id=staff.organization_id, lead_id=lead.id, patient_id=patient.id))
    return detail_of(db, patient), 201
