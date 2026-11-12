from flask import current_app, g
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel

from app.identity.core.totp import decrypt_secret, encrypt_secret, new_secret, provisioning_uri
from app.identity.models import Account
from app.identity.session import current_account_id
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse

api = APIBlueprint(
    "auth_enroll_totp", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class EnrollResponse(BaseModel):
    otpauth_uri: str


@api.post(
    "/api/auth/totp/enroll",
    responses={200: EnrollResponse, 401: ErrorResponse, 409: ErrorResponse},
)
def enroll_totp():
    """Start enrollment: store a new, still unconfirmed secret (or return the one already stored)."""
    account_id = current_account_id()
    db = get_session()
    set_tenant_context(db, organization_id=getattr(g, "organization_id", None), account_id=account_id)
    account = db.get(Account, account_id)
    if account is None:
        raise ApiError(401, "unauthenticated")
    if account.totp_enabled:
        raise ApiError(409, "totp_already_enabled")
    key = current_app.config["TOTP_ENCRYPTION_KEY"]
    if account.totp_secret_encrypted:
        secret = decrypt_secret(account.totp_secret_encrypted, key)
    else:
        secret = new_secret()
        account.totp_secret_encrypted = encrypt_secret(secret, key)
    return {"otpauth_uri": provisioning_uri(secret, account.email)}
