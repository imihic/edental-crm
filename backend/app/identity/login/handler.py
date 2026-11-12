from uuid import UUID

from app.compliance import AuditAction, record_audit
from app.identity.lookup import Membership, list_memberships
from app.identity.session import bind_staff_member, rotate_session
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import error_response


def invalid_credentials():
    return error_response(401, "invalid_credentials")


def audit_login_failed(account_id: UUID, detail: dict | None = None) -> None:
    db = get_session()
    for m in list_memberships(db, account_id):
        set_tenant_context(db, organization_id=m.organization_id, account_id=None)
        record_audit(
            db,
            organization_id=m.organization_id,
            action=AuditAction.LOGIN_FAILED,
            entity_type="account",
            entity_id=account_id,
            staff_member_id=m.staff_member_id,
            account_id=account_id,
            detail=detail,
        )
        db.flush()
    set_tenant_context(db, organization_id=None, account_id=None)


def continue_sign_in(
    account_id: UUID, memberships: list[Membership], authenticated_at: int, credentials_at: int
):
    if not memberships:
        return invalid_credentials()
    rotate_session(account_id=account_id, authenticated_at=authenticated_at, credentials_at=credentials_at)
    if len(memberships) == 1:
        bind_staff_member(account_id, memberships[0])
        return {"status": "ok"}
    return {
        "status": "choose_organization",
        "organizations": [{"id": str(m.organization_id), "name": m.organization_name} for m in memberships],
    }
