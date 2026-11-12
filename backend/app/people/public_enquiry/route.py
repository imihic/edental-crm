from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import text

from app.compliance import AuditAction, record_audit
from app.people.enquiry_form_service import KEY_FORMAT
from app.people.lead_create.handler import clean_contact, record_enquiry
from app.people.models import Consent
from app.people.patient_service import validation_failed
from app.people.schemas import PublicEnquiryIn, PublicEnquiryReceived, PublicFormInfo, PublicFormPath
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse

api = APIBlueprint(
    "public_enquiry", __name__, abp_tags=[Tag(name="public")], abp_responses=VALIDATION_ERROR_RESPONSES
)


def _lookup(key: str):
    if not KEY_FORMAT.match(key):
        raise ApiError(404, "not_found")
    row = get_session().execute(text("SELECT * FROM public_enquiry_form(:key)"), {"key": key}).first()
    if row is None:
        raise ApiError(404, "not_found")
    return row


@api.get(
    "/api/public/enquiry-forms/<string:key>",
    responses={200: PublicFormInfo, 404: ErrorResponse},
)
def get_public_form(path: PublicFormPath):
    """What the public form shows: the Clinic's and Organization's names and the language. Nothing else."""
    form = _lookup(path.key)
    return PublicFormInfo(
        clinic_name=form.clinic_name, organization_name=form.organization_name, locale=form.locale
    ).model_dump(mode="json")


@api.post(
    "/api/public/enquiry-forms/<string:key>/enquiries",
    responses={202: PublicEnquiryReceived, 404: ErrorResponse},
)
def submit_public_enquiry(path: PublicFormPath, body: PublicEnquiryIn):
    """Send an Enquiry without signing in. Attaches to the Patient with this e-mail, otherwise creates a Lead."""
    db = get_session()
    form = _lookup(path.key)
    set_tenant_context(db, organization_id=form.organization_id, account_id=None)
    received = PublicEnquiryReceived(status="received").model_dump(mode="json"), 202
    if body.website.strip():
        return received
    phone, email, bad = clean_contact(db, phone=body.phone, email=body.email, clinic_id=form.clinic_id)
    if bad:
        return validation_failed(bad)
    result = record_enquiry(
        db,
        full_name=body.full_name,
        phone=phone,
        email=email,
        clinic_id=form.clinic_id,
        source="website_form",
        message=body.message,
        preferred_contact_time=body.preferred_contact_time,
        staff_member_id=None,
        marketing_consent_requested=body.marketing_consent,
    )
    if body.marketing_consent and result.lead_id is not None:
        db.add(
            Consent(
                organization_id=form.organization_id,
                patient_id=None,
                lead_id=result.lead_id,
                purpose="marketing",
                granted=True,
                source="enquiry_form",
                recorded_by_staff_member_id=None,
            )
        )
    record_audit(
        db,
        organization_id=form.organization_id,
        action=AuditAction.CREATE,
        entity_type="enquiry",
        entity_id=result.enquiry_id,
        detail={"source": "website_form"},
    )
    return received
