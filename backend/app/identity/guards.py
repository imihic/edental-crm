import hmac
from functools import wraps

from flask import g, request, session

from app.identity.core.permissions import has_any_role, requires_totp
from app.identity.core.roles import Role
from app.identity.models import Account
from app.identity.session import current_staff
from app.platform.db import get_session
from app.platform.errors import ApiError

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_EXEMPT_PATHS = frozenset({"/api/auth/login", "/api/auth/totp"})
PUBLIC_PREFIX = "/api/public/"
EXPECTED_ORGANIZATION_HEADER = "X-Expected-Organization"
TOTP_FENCE_ALLOWED_PATHS = frozenset(
    {
        "/api/health",
        "/api/auth/me",
        "/api/auth/logout",
        "/api/auth/csrf",
        "/api/auth/organizations",
        "/api/auth/organization",
        "/api/auth/totp/enroll",
        "/api/auth/totp/confirm",
    }
)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        current_staff()
        return view(*args, **kwargs)

    return wrapper


def require_role(*roles: Role):
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not has_any_role(current_staff().roles, *roles):
                raise ApiError(403, "forbidden")
            return view(*args, **kwargs)

        return wrapper

    return decorator


def enforce_json_and_csrf() -> None:
    if request.method in SAFE_METHODS or not request.path.startswith("/api/"):
        return
    if request.routing_exception is not None:
        return
    if not request.is_json:
        raise ApiError(415, "json_required")
    if "account_id" not in session or request.path in CSRF_EXEMPT_PATHS or request.path.startswith(PUBLIC_PREFIX):
        return
    expected = session.get("csrf_token") or ""
    sent = request.headers.get("X-CSRF-Token", "")
    if not expected or not hmac.compare_digest(expected.encode(), sent.encode()):
        raise ApiError(403, "csrf_failed")


def enforce_totp_enrollment() -> None:
    staff = getattr(g, "staff", None)
    if staff is None or not request.path.startswith("/api/") or request.routing_exception is not None:
        return
    if not request.path.startswith(("/api/auth/", PUBLIC_PREFIX)) and request.path != "/api/health":
        expected_org = request.headers.get(EXPECTED_ORGANIZATION_HEADER)
        if expected_org is not None and expected_org != str(staff.organization_id):
            raise ApiError(409, "organization_changed")
    if request.path in TOTP_FENCE_ALLOWED_PATHS or request.path.startswith(PUBLIC_PREFIX) or not requires_totp(staff.roles):
        return
    account = get_session().get(Account, staff.account_id)
    if account is None or not account.totp_enabled:
        raise ApiError(403, "totp_enrollment_required")
