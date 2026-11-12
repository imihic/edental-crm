from uuid import UUID

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.identity import login_required
from app.people.core.lead_stages import STAGES
from app.people.models import Lead
from app.people.schemas import LeadListResponse, LeadStage, LeadSummary, lead_summary_of
from app.people.search import search_predicate
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint("leads_list", __name__, abp_tags=[Tag(name="leads")], abp_responses=VALIDATION_ERROR_RESPONSES)


class LeadListQuery(BaseModel):
    stage: LeadStage | None = None
    q: str = Field(default="", max_length=100)
    clinic_id: UUID | None = None
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=25, ge=1, le=100)


@api.get("/api/leads", responses={200: LeadListResponse, 401: ErrorResponse})
@login_required
def list_leads(query: LeadListQuery):
    """Leads (newest first) with per-stage counts that ignore the `stage` filter; not audited."""
    filters = [Lead.retired_at.is_(None)]
    match = search_predicate(Lead, query.q)
    if match is not None:
        filters.append(match)
    if query.clinic_id is not None:
        filters.append(Lead.clinic_id == query.clinic_id)
    db = get_session()
    counts = dict.fromkeys(STAGES, 0)
    counts.update(dict(db.execute(select(Lead.stage, func.count()).where(*filters).group_by(Lead.stage)).all()))
    page_filters = filters + ([Lead.stage == query.stage] if query.stage else [])
    total = counts[query.stage] if query.stage else sum(counts.values())
    rows = db.scalars(
        select(Lead)
        .where(*page_filters)
        .order_by(Lead.created_at.desc(), Lead.id)
        .limit(query.page_size)
        .offset((query.page - 1) * query.page_size)
    ).all()
    return LeadListResponse(
        items=[LeadSummary(**lead_summary_of(lead)) for lead in rows], total=total, counts=counts
    ).model_dump(mode="json")
