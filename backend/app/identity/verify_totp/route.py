from flask import session
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.identity.login.handler import audit_login_failed, continue_sign_in
from app.identity.login.route import LoginResponse
from app.identity.lookup import list_memberships
from app.identity.models import Account
from app.identity.session import parse_uuid
from app.identity.totp_codes import accept_totp_code
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response

api = APIBlueprint(
    "auth_verify_totp", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class TotpBody(BaseModel):
    code: str = Field(max_length=16)


@api.post(
    "/api/auth/totp",
    responses={200: LoginResponse, 401: ErrorResponse},
)
def verify_totp(body: TotpBody):
    """Second step of sign-in: a valid code continues exactly like a password-only login."""
    account_id = parse_uuid(session.get("pending_account_id"))
    authenticated_at = session.get("authenticated_at")
    credentials_at = session.get("credentials_at")
    if account_id is None or not isinstance(authenticated_at, int) or not isinstance(credentials_at, int):
        raise ApiError(401, "unauthenticated")
    db = get_session()
    set_tenant_context(db, organization_id=None, account_id=account_id)
    account = db.get(Account, account_id)
    if account is None or not account.totp_enabled or not accept_totp_code(db, account, body.code.strip()):
        audit_login_failed(account_id, {"factor": "totp"})
        return error_response(401, "invalid_code")
    return continue_sign_in(account_id, list_memberships(db, account_id), authenticated_at, credentials_at)
