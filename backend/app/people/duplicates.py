from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.people.core.duplicates import Candidate, match_reasons
from app.people.models import Lead, Patient
from app.people.schemas import DuplicateOut

MAX_DUPLICATES = 20
PREFILTER_LIMIT = 50


def find_possible_duplicates(
    session: Session,
    candidate: Candidate,
    *,
    exclude_patient_id: UUID | None = None,
    exclude_lead_id: UUID | None = None,
    include_leads: bool = True,
) -> list[DuplicateOut]:
    exact = []
    if candidate.oib:
        exact.append(Patient.oib == candidate.oib)
    if candidate.email:
        exact.append(Patient.email == candidate.email)
    conditions = list(exact)
    if candidate.date_of_birth is not None:
        conditions.append(
            and_(
                func.f_unaccent(func.lower(Patient.last_name)) == func.f_unaccent(func.lower(candidate.last_name)),
                Patient.date_of_birth == candidate.date_of_birth,
            )
        )
    found = _patient_matches(session, candidate, conditions, exact, exclude_patient_id) if conditions else []
    if include_leads and candidate.email:
        found += _lead_matches(session, candidate.email, exclude_lead_id=exclude_lead_id)
    return found[:MAX_DUPLICATES]


def _patient_matches(
    session: Session, candidate: Candidate, conditions: list, exact: list, exclude_patient_id: UUID | None
) -> list[DuplicateOut]:
    query = (
        select(Patient)
        .where(Patient.retired_at.is_(None), or_(*conditions))
        .order_by(case((or_(*exact), 0), else_=1) if exact else Patient.created_at, Patient.created_at)
        .limit(PREFILTER_LIMIT)
    )
    if exclude_patient_id is not None:
        query = query.where(Patient.id != exclude_patient_id)
    found = []
    for p in session.scalars(query):
        reasons = match_reasons(
            candidate, Candidate(p.first_name, p.last_name, p.date_of_birth, p.email, p.oib)
        )
        if reasons:
            found.append(
                DuplicateOut(kind="patient", id=p.id, display_name=f"{p.first_name} {p.last_name}", reasons=reasons)
            )
    return found


def _lead_matches(session: Session, email: str, *, exclude_lead_id: UUID | None = None) -> list[DuplicateOut]:
    query = (
        select(Lead)
        .where(Lead.retired_at.is_(None), Lead.stage != "converted", Lead.email == email)
        .order_by(Lead.created_at, Lead.id)
        .limit(PREFILTER_LIMIT)
    )
    if exclude_lead_id is not None:
        query = query.where(Lead.id != exclude_lead_id)
    return [DuplicateOut(kind="lead", id=lead.id, display_name=lead.full_name, reasons=["email"]) for lead in session.scalars(query)]


def find_duplicates_of_lead(session: Session, lead: Lead) -> list[DuplicateOut]:
    if not lead.email:
        return []
    patients = session.scalars(
        select(Patient)
        .where(Patient.retired_at.is_(None), Patient.email == lead.email)
        .order_by(Patient.created_at, Patient.id)
        .limit(PREFILTER_LIMIT)
    )
    found = [
        DuplicateOut(kind="patient", id=p.id, display_name=f"{p.first_name} {p.last_name}", reasons=["email"])
        for p in patients
    ]
    found += _lead_matches(session, lead.email, exclude_lead_id=lead.id)
    return found[:MAX_DUPLICATES]
