from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.people.consent_service import current_consent
from app.people.duplicates import find_duplicates_of_lead
from app.people.models import Enquiry, Lead
from app.people.schemas import LeadDetail, enquiry_out, lead_summary_of
from app.platform.errors import ApiError, error_response


def load_lead(session: Session, lead_id: UUID, *, for_update: bool = False) -> Lead:
    if for_update:
        lead = session.scalars(
            select(Lead).where(Lead.id == lead_id).with_for_update().execution_options(populate_existing=True)
        ).one_or_none()
    else:
        lead = session.get(Lead, lead_id)
    if lead is None:
        raise ApiError(404, "not_found")
    return lead


def merged_lead_response(lead: Lead):
    return error_response(410, "merged", merged_into=str(lead.retired_into_patient_id))


def lead_detail_of(session: Session, lead: Lead) -> dict:
    enquiries = session.scalars(
        select(Enquiry).where(Enquiry.lead_id == lead.id).order_by(Enquiry.received_at.desc(), Enquiry.id)
    ).all()
    return LeadDetail(
        **lead_summary_of(lead),
        lost_note=lead.lost_note,
        converted_patient_id=lead.converted_patient_id,
        updated_at=lead.updated_at,
        enquiries=[enquiry_out(e) for e in enquiries],
        possible_duplicates=find_duplicates_of_lead(session, lead),
        consent=current_consent(session, lead_id=lead.id),
    ).model_dump(mode="json")
