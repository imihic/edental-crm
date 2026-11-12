from uuid import UUID

from flask import g
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.compliance import AuditAction, record_audit
from app.identity.lookup import list_memberships
from app.identity.models import Account
from app.identity.schemas import OkResponse
from app.identity.session import current_account_id
from app.identity.totp_codes import accept_totp_code
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse

api = APIBlueprint(
    "auth_confirm_totp", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class ConfirmBody(BaseModel):
    code: str = Field(max_length=16)


@api.post(
    "/api/auth/totp/confirm",
    responses={200: OkResponse, 400: ErrorResponse, 401: ErrorResponse},
)
def confirm_totp(body: ConfirmBody):
    """Prove the authenticator app holds the pending secret, then require it at every sign-in."""
    account_id = current_account_id()
    organization_id = getattr(g, "organization_id", None)
    db = get_session()
    set_tenant_context(db, organization_id=organization_id, account_id=account_id)
    account = db.get(Account, account_id)
    if account is None:
        raise ApiError(401, "unauthenticated")
    if account.totp_enabled or not account.totp_secret_encrypted:
        raise ApiError(400, "invalid_code")
    if not accept_totp_code(db, account, body.code.strip()):
        raise ApiError(400, "invalid_code")
    account.totp_enabled = True
    db.flush()
    _audit_totp_enabled(db, account_id)
    set_tenant_context(db, organization_id=organization_id, account_id=account_id)
    return {"status": "ok"}


def _audit_totp_enabled(db: Session, account_id: UUID) -> None:
    for m in list_memberships(db, account_id):
        set_tenant_context(db, organization_id=m.organization_id, account_id=account_id)
        record_audit(
            db,
            organization_id=m.organization_id,
            action=AuditAction.UPDATE,
            entity_type="account",
            entity_id=account_id,
            staff_member_id=m.staff_member_id,
            account_id=account_id,
            detail={"fields": ["totp"]},
        )
        db.flush()
