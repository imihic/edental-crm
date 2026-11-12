from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.people.core.phones import InvalidPhone, normalize_phone
from app.people.models import Enquiry, Lead, Patient
from app.people.patient_service import clinic_name


@dataclass(frozen=True)
class EnquiryResult:
    attached_to: Literal["lead", "patient"]
    lead_id: UUID | None
    patient_id: UUID | None
    enquiry_id: UUID


def clean_contact(
    session: Session, *, phone: str | None, email: str | None, clinic_id: UUID
) -> tuple[str | None, str | None, list[str]]:
    bad: list[str] = []
    email = (email or "").strip() or None
    phone_e164 = None
    if phone and phone.strip():
        try:
            phone_e164 = normalize_phone(phone.strip())
        except InvalidPhone:
            bad.append("phone")
    if phone_e164 is None and email is None and "phone" not in bad:
        bad += ["phone", "email"]
    if clinic_name(session, clinic_id) is None:
        bad.append("clinic_id")
    return phone_e164, email, bad


def record_enquiry(
    session: Session,
    *,
    full_name: str,
    phone: str | None,
    email: str | None,
    clinic_id: UUID,
    source: str,
    message: str,
    preferred_contact_time: str | None,
    staff_member_id: UUID | None,
    marketing_consent_requested: bool = False,
) -> EnquiryResult:
    organization_id = session.execute(text("SELECT app_current_org()")).scalar_one()
    if organization_id is None:
        raise RuntimeError("record_enquiry needs a tenant context: set the Organization before calling it")
    matches: list[Patient] = []
    if email:
        matches = list(
            session.scalars(
                select(Patient).where(Patient.email == email, Patient.retired_at.is_(None)).limit(2)
            )
        )
    lead = None
    patient = matches[0] if len(matches) == 1 else None
    if patient is None:
        lead = Lead(
            organization_id=organization_id,
            full_name=full_name,
            phone_e164=phone,
            email=email,
            clinic_id=clinic_id,
        )
        session.add(lead)
        session.flush()
    enquiry = Enquiry(
        organization_id=organization_id,
        lead_id=lead.id if lead else None,
        patient_id=patient.id if patient else None,
        clinic_id=clinic_id,
        source=source,
        message=message,
        preferred_contact_time=preferred_contact_time,
        created_by_staff_member_id=staff_member_id,
        marketing_consent_requested=marketing_consent_requested,
    )
    session.add(enquiry)
    session.flush()
    return EnquiryResult(
        attached_to="lead" if lead else "patient",
        lead_id=lead.id if lead else None,
        patient_id=patient.id if patient else None,
        enquiry_id=enquiry.id,
    )
