from flask_openapi3 import APIBlueprint, Tag

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.core.lead_stages import InvalidTransition, LostReasonRequired, transition
from app.people.lead_service import lead_detail_of, load_lead, merged_lead_response
from app.people.patient_service import validation_failed
from app.people.schemas import LeadDetail, LeadPath, LeadStageIn, MergedResponse
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse, error_response

api = APIBlueprint("lead_stage", __name__, abp_tags=[Tag(name="leads")], abp_responses=VALIDATION_ERROR_RESPONSES)


@api.post(
    "/api/leads/<uuid:lead_id>/stage",
    responses={200: LeadDetail, 401: ErrorResponse, 404: ErrorResponse, 409: ErrorResponse, 410: MergedResponse},
)
@login_required
def change_stage(path: LeadPath, body: LeadStageIn):
    """Move a Lead along the stage machine (`converted` only through Conversion). Audited as an update."""
    db = get_session()
    staff = current_staff()
    lead = load_lead(db, path.lead_id, for_update=True)
    if lead.retired_at is not None:
        return merged_lead_response(lead)
    try:
        transition(lead.stage, body.stage, lost_reason=body.lost_reason)
    except InvalidTransition:
        return error_response(409, "invalid_transition")
    except LostReasonRequired:
        return validation_failed(["lost_reason"])
    lead.stage = body.stage
    lost = body.stage == "lost"
    lead.lost_reason = body.lost_reason if lost else None
    lead.lost_note = ((body.lost_note or "").strip() or None) if lost else None
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
    db.refresh(lead)
    return lead_detail_of(db, lead)
