from uuid import uuid4

from sqlalchemy.orm import Session

from app.compliance import AuditAction, record_audit
from app.identity.core.passwords import MIN_PASSWORD_LENGTH, hash_password
from app.identity.core.roles import Role
from app.identity.lookup import find_account_for_login
from app.identity.models import Account, Clinic, Organization, StaffClinic, StaffMember
from app.platform.db import set_tenant_context


def create_organization(
    session: Session,
    *,
    name: str,
    clinic_name: str,
    manager_email: str,
    manager_name: str,
    manager_password: str | None,
) -> Organization:
    try:
        org = _create(session, name, clinic_name, manager_email, manager_name, manager_password)
        session.commit()
        return org
    except BaseException:
        session.rollback()
        raise


def _create(
    session: Session,
    name: str,
    clinic_name: str,
    manager_email: str,
    manager_name: str,
    manager_password: str | None,
) -> Organization:
    email = manager_email.strip().lower()
    candidate = find_account_for_login(session, email)
    if candidate is not None:
        if manager_password is not None:
            raise ValueError("account_exists")
        account_id = candidate.id
    else:
        if manager_password is None or len(manager_password) < MIN_PASSWORD_LENGTH:
            raise ValueError("password_too_short")
        account_id = uuid4()

    org_id = uuid4()
    set_tenant_context(session, organization_id=org_id, account_id=account_id)
    if candidate is None:
        session.add(Account(id=account_id, email=email, password_hash=hash_password(manager_password)))
    org = Organization(id=org_id, name=name)
    session.add(org)
    session.flush()
    clinic = Clinic(organization_id=org_id, name=clinic_name)
    staff = StaffMember(
        organization_id=org_id, account_id=account_id, full_name=manager_name, roles=[Role.CLINIC_MANAGER]
    )
    session.add_all([clinic, staff])
    session.flush()
    session.add(StaffClinic(organization_id=org_id, staff_member_id=staff.id, clinic_id=clinic.id))
    for entity_type, entity_id in (("organization", org_id), ("clinic", clinic.id), ("staff_member", staff.id)):
        record_audit(
            session,
            organization_id=org_id,
            action=AuditAction.CREATE,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    session.flush()
    return org
