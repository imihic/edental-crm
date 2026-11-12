import secrets
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from flask import current_app, g, session
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance import AuditAction, record_audit
from app.identity.lookup import Membership
from app.identity.models import Account, StaffMember
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import ApiError

PENDING_TOTP_LIFETIME = timedelta(minutes=10)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def parse_uuid(value) -> UUID | None:
    try:
        return UUID(value) if value else None
    except (TypeError, ValueError):
        return None


def now() -> float:
    return time.time()


def rotate_session(**values) -> None:
    session.clear()
    session.update(
        {k: v if isinstance(v, int) else str(v) for k, v in values.items() if v is not None}
    )
    current_app.session_interface.regenerate(session)


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def credentials_stamp(db: Session, account_id: UUID) -> int | None:
    set_tenant_context(db, organization_id=None, account_id=account_id)
    changed = db.scalar(select(Account.credentials_changed_at).where(Account.id == account_id))
    return None if changed is None else (changed - _EPOCH) // timedelta(microseconds=1)


def start_pending_totp(account_id: UUID, credentials_at: int) -> None:
    rotate_session(pending_account_id=account_id, authenticated_at=int(now()), credentials_at=credentials_at)


def sign_in_time() -> int:
    return int(now())


def _authenticated_at() -> int | None:
    value = session.get("authenticated_at")
    return value if isinstance(value, int) else None


def _credentials_at() -> int | None:
    value = session.get("credentials_at")
    return value if isinstance(value, int) else None


def _expired() -> bool:
    started = _authenticated_at()
    if "account_id" in session:
        lifetime = current_app.permanent_session_lifetime
    else:
        lifetime = PENDING_TOTP_LIFETIME
    return started is None or now() - started > lifetime.total_seconds()


def bind_staff_member(account_id: UUID, membership: Membership) -> None:
    rotate_session(
        account_id=account_id,
        staff_member_id=membership.staff_member_id,
        organization_id=membership.organization_id,
        authenticated_at=_authenticated_at(),
        credentials_at=_credentials_at(),
    )
    db = get_session()
    set_tenant_context(db, organization_id=membership.organization_id, account_id=account_id)
    record_audit(
        db,
        organization_id=membership.organization_id,
        action=AuditAction.LOGIN,
        entity_type="staff_member",
        entity_id=membership.staff_member_id,
        staff_member_id=membership.staff_member_id,
        account_id=account_id,
    )
    g.organization_id = membership.organization_id
    g.staff_member_id = membership.staff_member_id


def load_current_staff() -> None:
    g.staff = None
    if "account_id" not in session and "pending_account_id" not in session:
        return
    if _expired():
        session.clear()
        return
    account_id = parse_uuid(session.get("account_id"))
    subject_id = account_id or parse_uuid(session.get("pending_account_id"))
    db = get_session()
    stamp = credentials_stamp(db, subject_id) if subject_id is not None else None
    if stamp is None or stamp != _credentials_at():
        session.clear()
        set_tenant_context(db, organization_id=None, account_id=None)
        return
    if account_id is None:
        set_tenant_context(db, organization_id=None, account_id=None)
        return
    organization_id = parse_uuid(session.get("organization_id"))
    staff_member_id = parse_uuid(session.get("staff_member_id"))
    set_tenant_context(db, organization_id=organization_id, account_id=account_id)
    if staff_member_id is None:
        return
    staff = db.get(StaffMember, staff_member_id)
    if (
        staff is None
        or not staff.is_active
        or staff.account_id != account_id
        or staff.organization_id != organization_id
    ):
        session.clear()
        set_tenant_context(db, organization_id=None, account_id=None)
        return
    g.staff = staff
    g.organization_id = organization_id
    g.staff_member_id = staff_member_id


def current_staff() -> StaffMember:
    staff = getattr(g, "staff", None)
    if staff is None:
        raise ApiError(401, "unauthenticated")
    return staff


def current_account_id() -> UUID:
    account_id = parse_uuid(session.get("account_id"))
    if account_id is None:
        raise ApiError(401, "unauthenticated")
    return account_id
