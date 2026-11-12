from datetime import UTC, datetime
from uuid import uuid4

from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.compliance import AuditAction, record_audit
from app.identity.core.passwords import MIN_PASSWORD_LENGTH, hash_password, verify_password
from app.identity.login.handler import audit_login_failed
from app.identity.invitation_service import TOKEN_FORMAT, hash_token
from app.identity.lookup import find_account_for_login
from app.identity.models import Account, Invitation, StaffClinic, StaffMember
from app.identity.schemas_staff import AcceptedOut, AcceptInvitationIn, InvitationTokenPath, PublicInvitationOut
from app.identity.totp_codes import accept_totp_code
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response

api = APIBlueprint(
    "public_invitation", __name__, abp_tags=[Tag(name="public")], abp_responses=VALIDATION_ERROR_RESPONSES
)

GONE = {"accepted": "invitation_used", "revoked": "invitation_revoked"}


def _gone(status: str, expires_at: datetime) -> str | None:
    if status in GONE:
        return GONE[status]
    if expires_at <= datetime.now(UTC):
        return "invitation_expired"
    return None


def _lookup(token: str):
    if not TOKEN_FORMAT.match(token):
        raise ApiError(404, "not_found")
    row = get_session().execute(text("SELECT * FROM public_invitation(:h)"), {"h": hash_token(token)}).first()
    if row is None:
        raise ApiError(404, "not_found")
    if (code := _gone(row.status, row.expires_at)) is not None:
        raise ApiError(410, code)
    return row


@api.get(
    "/api/public/invitations/<string:token>",
    responses={200: PublicInvitationOut, 404: ErrorResponse, 410: ErrorResponse},
)
def get_public_invitation(path: InvitationTokenPath):
    """What the invited person sees before choosing a password: Organization, their e-mail and name."""
    row = _lookup(path.token)
    exists = find_account_for_login(get_session(), row.email) is not None
    return PublicInvitationOut(
        organization_name=row.organization_name, email=row.email, full_name=row.full_name, account_exists=exists
    ).model_dump(mode="json")


@api.post(
    "/api/public/invitations/<string:token>/accept",
    responses={
        200: AcceptedOut,
        401: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        410: ErrorResponse,
    },
)
def accept_invitation(path: InvitationTokenPath, body: AcceptInvitationIn):
    """Become a Staff Member. A new Account sets a password; an existing one proves it (and TOTP). No session."""
    db = get_session()
    row = _lookup(path.token)
    org = row.organization_id
    set_tenant_context(db, organization_id=org, account_id=None)

    candidate = find_account_for_login(db, row.email)
    if candidate is not None:
        if not verify_password(candidate.password_hash, body.password):
            audit_login_failed(candidate.id, {"via": "invitation"})
            return error_response(401, "invalid_credentials")
        account_id = candidate.id
        set_tenant_context(db, organization_id=org, account_id=account_id)
        if candidate.totp_enabled:
            code = (body.code or "").strip()
            account = db.get(Account, account_id)
            if not code or account is None or not accept_totp_code(db, account, code):
                audit_login_failed(account_id, {"via": "invitation", "factor": "totp"})
                return error_response(401, "invalid_code")
        if db.scalar(
            select(StaffMember.id).where(StaffMember.account_id == account_id, StaffMember.organization_id == org)
        ):
            raise ApiError(409, "already_staff")
    else:
        if len(body.password) < MIN_PASSWORD_LENGTH:
            return error_response(422, "validation_error", fields=["password"])
        account_id = uuid4()

    invitation = db.scalar(select(Invitation).where(Invitation.id == row.id))

    staff_id = uuid4()
    claimed = db.execute(
        text(
            "UPDATE invitations SET status = 'accepted', accepted_at = now(), accepted_staff_member_id = :s "
            "WHERE id = :id AND status = 'pending' AND expires_at > now()"
        ),
        {"s": staff_id, "id": row.id},
    )
    if claimed.rowcount != 1:
        current = db.execute(
            text("SELECT status, expires_at FROM invitations WHERE id = :id"), {"id": row.id}
        ).one()
        raise ApiError(410, _gone(current.status, current.expires_at) or "invitation_expired")

    if candidate is None:
        set_tenant_context(db, organization_id=org, account_id=account_id)
        db.add(Account(id=account_id, email=row.email, password_hash=hash_password(body.password)))
        try:
            db.flush()
        except IntegrityError:
            raise ApiError(409, "account_exists_retry") from None

    db.add(
        StaffMember(id=staff_id, organization_id=org, account_id=account_id, full_name=row.full_name, roles=list(invitation.roles))
    )
    db.flush()
    db.add_all(StaffClinic(organization_id=org, staff_member_id=staff_id, clinic_id=cid) for cid in invitation.clinic_ids)
    record_audit(
        db,
        organization_id=org,
        action=AuditAction.CREATE,
        entity_type="staff_member",
        entity_id=staff_id,
        staff_member_id=staff_id,
        account_id=account_id,
    )
    return AcceptedOut(status="accepted").model_dump(mode="json")
