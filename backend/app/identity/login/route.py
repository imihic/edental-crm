from typing import Literal

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field

from app.identity.core.passwords import DUMMY_HASH, verify_password
from app.identity.login.handler import audit_login_failed, continue_sign_in, invalid_credentials
from app.identity.lookup import find_account_for_login, list_memberships
from app.identity.schemas import OrganizationOut
from app.identity.session import credentials_stamp, sign_in_time, start_pending_totp
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "auth_login", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class LoginBody(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class LoginResponse(BaseModel):
    status: Literal["ok", "totp_required", "choose_organization"]
    organizations: list[OrganizationOut] | None = None


@api.post(
    "/api/auth/login",
    responses={200: LoginResponse, 401: ErrorResponse},
)
def login(body: LoginBody):
    db = get_session()
    account = find_account_for_login(db, body.email)
    if account is None:
        verify_password(DUMMY_HASH, body.password)
        return invalid_credentials()
    if not verify_password(account.password_hash, body.password):
        audit_login_failed(account.id)
        return invalid_credentials()
    memberships = list_memberships(db, account.id)
    if not memberships:
        return invalid_credentials()
    credentials_at = credentials_stamp(db, account.id)
    if credentials_at is None:
        return invalid_credentials()
    if account.totp_enabled:
        start_pending_totp(account.id, credentials_at)
        return {"status": "totp_required"}
    return continue_sign_in(account.id, memberships, sign_in_time(), credentials_at)
