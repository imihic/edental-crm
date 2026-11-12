from flask_openapi3 import APIBlueprint, Tag

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.lead_service import lead_detail_of, load_lead, merged_lead_response
from app.people.schemas import LeadDetail, LeadPath, MergedResponse
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint("lead_detail", __name__, abp_tags=[Tag(name="leads")], abp_responses=VALIDATION_ERROR_RESPONSES)


@api.get(
    "/api/leads/<uuid:lead_id>",
    responses={200: LeadDetail, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse},
)
@login_required
def get_lead(path: LeadPath):
    """A Lead with its Enquiries (newest first) and possible duplicates. Every read is audited as `view`."""
    db = get_session()
    staff = current_staff()
    lead = load_lead(db, path.lead_id)
    if lead.retired_at is not None:
        return merged_lead_response(lead)
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.VIEW,
        entity_type="lead",
        entity_id=lead.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
    )
    return lead_detail_of(db, lead)
