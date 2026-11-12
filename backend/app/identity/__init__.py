from flask import Flask

from app.identity.api import auth_api
from app.identity.core.roles import Role
from app.identity.guards import enforce_json_and_csrf, enforce_totp_enrollment, login_required, require_role
from app.identity.lookup import (
    AccountCandidate,
    Membership,
    find_account_for_login,
    list_memberships,
)
from app.identity.onboarding.cli import create_organization_command
from app.identity.onboarding.handler import create_organization
from app.identity.reset_password.cli import reset_password_command
from app.identity.reset_password.handler import reset_password
from app.identity.session import current_account_id, current_staff, load_current_staff


def init_identity(app: Flask) -> None:
    app.before_request(load_current_staff)
    app.before_request(enforce_totp_enrollment)
    app.before_request(enforce_json_and_csrf)
    app.register_api(auth_api)
    app.cli.add_command(create_organization_command)
    app.cli.add_command(reset_password_command)
    if app.config.get("TESTING"):
        app.add_url_rule(
            "/api/_test/protected", endpoint="_test_protected", view_func=login_required(lambda: {"ok": True})
        )


__all__ = [
    "Role",
    "AccountCandidate",
    "Membership",
    "create_organization",
    "current_account_id",
    "current_staff",
    "find_account_for_login",
    "init_identity",
    "list_memberships",
    "login_required",
    "require_role",
    "reset_password",
]
