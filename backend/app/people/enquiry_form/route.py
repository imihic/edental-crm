from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import text

from app.compliance import AuditAction, record_audit
from app.identity import Role, current_staff, login_required, require_role
from app.people.enquiry_form_service import clinic_exists, ensure_form, new_key
from app.people.schemas import ClinicPath, EnquiryFormOut
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse

api = APIBlueprint("enquiry_form", __name__, abp_tags=[Tag(name="enquiry-form")], abp_responses=VALIDATION_ERROR_RESPONSES)

RESPONSES = {200: EnquiryFormOut, 401: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse}


def _out(key: str, enabled: bool) -> dict:
    return EnquiryFormOut(key=key, path=f"/enquiry/{key}", enabled=enabled).model_dump(mode="json")


@api.get("/api/clinics/<uuid:clinic_id>/enquiry-form", responses=RESPONSES)
@login_required
@require_role(Role.CLINIC_MANAGER)
def get_enquiry_form(path: ClinicPath):
    """The Clinic's Enquiry Form key and public path; the form is created on the first call."""
    db = get_session()
    staff = current_staff()
    if not clinic_exists(db, path.clinic_id):
        raise ApiError(404, "not_found")
    _, key, enabled = ensure_form(db, organization_id=staff.organization_id, clinic_id=path.clinic_id)
    return _out(key, enabled)


@api.post("/api/clinics/<uuid:clinic_id>/enquiry-form/regenerate", responses=RESPONSES)
@login_required
@require_role(Role.CLINIC_MANAGER)
def regenerate_enquiry_form_key(path: ClinicPath):
    """Replace the key: the old one stops working at once. Audited `update` on entity enquiry_form."""
    db = get_session()
    staff = current_staff()
    if not clinic_exists(db, path.clinic_id):
        raise ApiError(404, "not_found")
    form_id, _, _ = ensure_form(db, organization_id=staff.organization_id, clinic_id=path.clinic_id)
    row = db.execute(
        text("UPDATE enquiry_forms SET key = :key, rotated_at = now() WHERE id = :id RETURNING key, enabled"),
        {"key": new_key(), "id": form_id},
    ).one()
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.UPDATE,
        entity_type="enquiry_form",
        entity_id=form_id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
        detail={"fields": ["key"]},
    )
    return _out(row.key, row.enabled)
