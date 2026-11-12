from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.people.core.consent import current_state
from app.people.models import Consent
from app.people.schemas import ConsentOut


def _subject_filter(patient_id: UUID | None, lead_id: UUID | None):
    return Consent.patient_id == patient_id if patient_id is not None else Consent.lead_id == lead_id


def current_consent(session: Session, *, patient_id: UUID | None = None, lead_id: UUID | None = None) -> dict:
    latest = session.scalars(
        select(Consent)
        .where(_subject_filter(patient_id, lead_id))
        .ext(distinct_on(Consent.purpose))
        .order_by(Consent.purpose, Consent.recorded_at.desc(), Consent.id.desc())
    ).all()
    return current_state(latest)


def consent_history(session: Session, *, patient_id: UUID | None = None, lead_id: UUID | None = None) -> list[Consent]:
    return list(
        session.scalars(
            select(Consent)
            .where(_subject_filter(patient_id, lead_id))
            .order_by(Consent.recorded_at.desc(), Consent.id.desc())
        )
    )


def consent_out(c: Consent) -> ConsentOut:
    return ConsentOut(
        id=c.id,
        purpose=c.purpose,
        granted=c.granted,
        source=c.source,
        given_by_guardian_link_id=c.given_by_guardian_link_id,
        carried_from_consent_id=c.carried_from_consent_id,
        recorded_by_staff_member_id=c.recorded_by_staff_member_id,
        recorded_at=c.recorded_at,
    )
