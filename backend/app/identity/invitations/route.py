from datetime import UTC, datetime

from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.compliance import AuditAction, record_audit
from app.identity.core.roles import Role
from app.identity.guards import login_required, require_role
from app.identity.invitation_service import INVITATION_TTL, hash_token, new_token, now
from app.identity.models import Account, Invitation, StaffMember
from app.identity.schemas_staff import (
    InvitationCreatedOut,
    InvitationIn,
    InvitationItemOut,
    InvitationListOut,
    InvitationPath,
)
from app.identity.session import current_staff
from app.identity.staff_service import all_clinics_of_organization, dedupe
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response

api = APIBlueprint("invitations", __name__, abp_tags=[Tag(name="invitations")], abp_responses=VALIDATION_ERROR_RESPONSES)

ERRORS = {401: ErrorResponse, 403: ErrorResponse}


@api.post("/api/invitations", responses={201: InvitationCreatedOut, 409: ErrorResponse, **ERRORS})
@login_required
@require_role(Role.CLINIC_MANAGER)
def create_invitation(body: InvitationIn):
    """Invite someone as a Staff Member. The link (with the token) is in this response only."""
    db = get_session()
    me = current_staff()
    org = me.organization_id
    if not all_clinics_of_organization(db, org, body.clinic_ids):
        return error_response(422, "validation_error", fields=["clinic_ids"])
    if db.scalar(
        select(StaffMember.id)
        .join(Account, Account.id == StaffMember.account_id)
        .where(StaffMember.organization_id == org, Account.email == body.email)
    ):
        raise ApiError(409, "already_staff")
    db.execute(
        update(Invitation)
        .where(
            Invitation.organization_id == org,
            Invitation.email == body.email,
            Invitation.status == "pending",
            Invitation.expires_at <= now(),
        )
        .values(status="revoked")
        .execution_options(synchronize_session=False)
    )
    token = new_token()
    created = now()
    invitation = Invitation(
        organization_id=org,
        email=body.email,
        full_name=body.full_name,
        roles=dedupe(body.roles),
        clinic_ids=dedupe(body.clinic_ids),
        token_hash=hash_token(token),
        status="pending",
        expires_at=created + INVITATION_TTL,
        created_by_staff_member_id=me.id,
        created_at=created,
    )
    db.add(invitation)
    try:
        db.flush()
    except IntegrityError:
        raise ApiError(409, "already_invited") from None
    record_audit(
        db,
        organization_id=org,
        action=AuditAction.CREATE,
        entity_type="invitation",
        entity_id=invitation.id,
        staff_member_id=me.id,
        account_id=me.account_id,
        detail={"roles": [r.value for r in invitation.roles], "clinic_count": len(invitation.clinic_ids)},
    )
    out = InvitationCreatedOut(id=invitation.id, url=f"/invite/{token}", expires_at=invitation.expires_at)
    return out.model_dump(mode="json"), 201


@api.get("/api/invitations", responses={200: InvitationListOut, **ERRORS})
@login_required
@require_role(Role.CLINIC_MANAGER)
def list_invitations():
    """Pending, unexpired Invitations (never their tokens)."""
    rows = get_session().scalars(
        select(Invitation)
        .where(
            Invitation.organization_id == current_staff().organization_id,
            Invitation.status == "pending",
            Invitation.expires_at > datetime.now(UTC),
        )
        .order_by(Invitation.created_at, Invitation.id)
    )
    items = [
        InvitationItemOut(
            id=i.id,
            email=i.email,
            full_name=i.full_name,
            roles=list(i.roles),
            clinic_ids=list(i.clinic_ids),
            expires_at=i.expires_at,
            created_at=i.created_at,
        )
        for i in rows
    ]
    return InvitationListOut(items=items).model_dump(mode="json")


@api.delete(
    "/api/invitations/<uuid:invitation_id>",
    responses={204: None, 404: ErrorResponse, 409: ErrorResponse, **ERRORS},
)
@login_required
@require_role(Role.CLINIC_MANAGER)
def revoke_invitation(path: InvitationPath):
    """Revoke a pending Invitation; its link stops working. Revoking twice is a no-op."""
    db = get_session()
    me = current_staff()
    org = me.organization_id
    revoked = db.scalar(
        update(Invitation)
        .where(Invitation.id == path.invitation_id, Invitation.organization_id == org, Invitation.status == "pending")
        .values(status="revoked")
        .returning(Invitation.id)
        .execution_options(synchronize_session=False)
    )
    if revoked is None:
        status = db.scalar(
            select(Invitation.status).where(Invitation.id == path.invitation_id, Invitation.organization_id == org)
        )
        if status is None:
            raise ApiError(404, "not_found")
        if status == "accepted":
            raise ApiError(409, "invitation_used")
        return "", 204
    record_audit(
        db,
        organization_id=org,
        action=AuditAction.UPDATE,
        entity_type="invitation",
        entity_id=revoked,
        staff_member_id=me.id,
        account_id=me.account_id,
        detail={"fields": ["status"]},
    )
    return "", 204
