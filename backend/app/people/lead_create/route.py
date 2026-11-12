from flask_openapi3 import APIBlueprint, Tag

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.lead_create.handler import clean_contact, record_enquiry
from app.people.patient_service import validation_failed
from app.people.schemas import LeadCreate, LeadCreated
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint("lead_create", __name__, abp_tags=[Tag(name="leads")], abp_responses=VALIDATION_ERROR_RESPONSES)


@api.post("/api/leads", responses={201: LeadCreated, 401: ErrorResponse})
@login_required
def create_lead(body: LeadCreate):
    """Record an Enquiry: attaches to the Patient with this e-mail, otherwise creates a Lead. Audited `create`."""
    db = get_session()
    staff = current_staff()
    phone, email, bad = clean_contact(db, phone=body.phone, email=body.email, clinic_id=body.clinic_id)
    if bad:
        return validation_failed(bad)
    result = record_enquiry(
        db,
        full_name=body.full_name,
        phone=phone,
        email=email,
        clinic_id=body.clinic_id,
        source=body.source,
        message=body.message,
        preferred_contact_time=body.preferred_contact_time,
        staff_member_id=staff.id,
    )
    if result.attached_to == "lead":
        entity_type, entity_id = "lead", result.lead_id
    else:
        entity_type, entity_id = "enquiry", result.enquiry_id
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.CREATE,
        entity_type=entity_type,
        entity_id=entity_id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
    )
    return LeadCreated(
        attached_to=result.attached_to, lead_id=result.lead_id, patient_id=result.patient_id
    ).model_dump(mode="json", exclude_none=True), 201
