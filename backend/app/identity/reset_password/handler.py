from sqlalchemy import func
from sqlalchemy.orm import Session

from app.compliance import AuditAction, record_audit
from app.identity.core.passwords import MIN_PASSWORD_LENGTH, hash_password
from app.identity.lookup import find_account_for_login, list_memberships
from app.identity.models import Account
from app.platform.db import set_tenant_context


def reset_password(session: Session, *, email: str, new_password: str, reset_totp: bool) -> None:
    try:
        _reset(session, email, new_password, reset_totp)
        session.commit()
    except BaseException:
        session.rollback()
        raise


def _reset(session: Session, email: str, new_password: str, reset_totp: bool) -> None:
    candidate = find_account_for_login(session, email)
    if candidate is None:
        raise ValueError("account_not_found")
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise ValueError("password_too_short")

    set_tenant_context(session, organization_id=None, account_id=candidate.id)
    account = session.get(Account, candidate.id)
    account.password_hash = hash_password(new_password)
    account.credentials_changed_at = func.now()
    fields = ["password"]
    if reset_totp:
        account.totp_secret_encrypted = None
        account.totp_enabled = False
        account.totp_last_step = None
        fields.append("totp")
    session.flush()

    for m in list_memberships(session, candidate.id):
        set_tenant_context(session, organization_id=m.organization_id, account_id=candidate.id)
        record_audit(
            session,
            organization_id=m.organization_id,
            action=AuditAction.UPDATE,
            entity_type="account",
            entity_id=candidate.id,
            staff_member_id=m.staff_member_id,
            account_id=candidate.id,
            detail={"fields": fields},
        )
        session.flush()
