from flask import g, session
from flask_openapi3 import APIBlueprint, Tag

from app.compliance import AuditAction, record_audit
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES

api = APIBlueprint(
    "auth_logout", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


@api.post("/api/auth/logout", responses={204: None})
def logout():
    staff = getattr(g, "staff", None)
    if staff is not None:
        record_audit(
            get_session(),
            organization_id=staff.organization_id,
            action=AuditAction.LOGOUT,
            entity_type="staff_member",
            entity_id=staff.id,
            staff_member_id=staff.id,
            account_id=staff.account_id,
        )
    session.clear()
    return "", 204
