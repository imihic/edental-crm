from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.models import Account, Clinic, StaffClinic, StaffMember
from app.identity.schemas_staff import ClinicRefOut, StaffOut


def list_staff(db: Session, organization_id: UUID, staff_id: UUID | None = None) -> list[StaffOut]:
    query = (
        select(StaffMember, Account.email)
        .join(Account, Account.id == StaffMember.account_id)
        .where(StaffMember.organization_id == organization_id)
        .order_by(StaffMember.full_name, StaffMember.id)
        .execution_options(populate_existing=True)
    )
    if staff_id is not None:
        query = query.where(StaffMember.id == staff_id)
    rows = db.execute(query).all()
    clinics: dict[UUID, list[ClinicRefOut]] = {}
    links = db.execute(
        select(StaffClinic.staff_member_id, Clinic.id, Clinic.name)
        .join(Clinic, Clinic.id == StaffClinic.clinic_id)
        .where(StaffClinic.organization_id == organization_id)
        .order_by(Clinic.name, Clinic.id)
    )
    for member_id, clinic_id, name in links:
        clinics.setdefault(member_id, []).append(ClinicRefOut(id=clinic_id, name=name))
    return [
        StaffOut(
            id=m.id,
            full_name=m.full_name,
            email=email,
            roles=list(m.roles),
            clinics=clinics.get(m.id, []),
            is_active=m.is_active,
        )
        for m, email in rows
    ]


def all_clinics_of_organization(db: Session, organization_id: UUID, clinic_ids: list[UUID]) -> bool:
    wanted = set(clinic_ids)
    found = set(
        db.scalars(select(Clinic.id).where(Clinic.organization_id == organization_id, Clinic.id.in_(wanted)))
    )
    return found == wanted


def dedupe(items: list) -> list:
    return list(dict.fromkeys(items))
