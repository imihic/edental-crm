from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.people.models import Contact, GuardianLink, Patient
from app.people.schemas import GuardianOfOut, GuardianOut


def guardians_of(session: Session, patient_id: UUID) -> list[GuardianOut]:
    rows = session.execute(
        select(GuardianLink, Patient, Contact)
        .outerjoin(Patient, Patient.id == GuardianLink.guardian_patient_id)
        .outerjoin(Contact, Contact.id == GuardianLink.guardian_contact_id)
        .where(GuardianLink.patient_id == patient_id, GuardianLink.ended_at.is_(None))
        .where(or_(GuardianLink.guardian_patient_id.is_(None), Patient.retired_at.is_(None)))
        .order_by(GuardianLink.created_at, GuardianLink.id)
    )
    return [guardian_out(link, guardian_patient, contact) for link, guardian_patient, contact in rows]


def guardian_out(link: GuardianLink, guardian_patient: Patient | None, contact: Contact | None) -> GuardianOut:
    if guardian_patient is not None:
        return GuardianOut(
            id=link.id,
            relationship=link.relationship,
            kind="patient",
            guardian_id=guardian_patient.id,
            display_name=f"{guardian_patient.first_name} {guardian_patient.last_name}",
            phone=guardian_patient.phone_e164,
            email=guardian_patient.email,
        )
    assert contact is not None
    return GuardianOut(
        id=link.id,
        relationship=link.relationship,
        kind="contact",
        guardian_id=contact.id,
        display_name=contact.full_name,
        phone=contact.phone_e164,
        email=contact.email,
    )


def guardian_of_list(session: Session, patient_id: UUID) -> list[GuardianOfOut]:
    rows = session.execute(
        select(Patient)
        .join(GuardianLink, GuardianLink.patient_id == Patient.id)
        .where(
            GuardianLink.guardian_patient_id == patient_id,
            GuardianLink.ended_at.is_(None),
            Patient.retired_at.is_(None),
        )
        .order_by(Patient.last_name, Patient.first_name, Patient.id)
    ).scalars()
    return [GuardianOfOut(patient_id=p.id, display_name=f"{p.first_name} {p.last_name}") for p in rows]
