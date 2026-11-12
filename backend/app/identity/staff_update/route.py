from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import any_, delete, select

from app.compliance import AuditAction, record_audit
from app.identity.core.roles import Role
from app.identity.guards import login_required, require_role
from app.identity.models import StaffClinic, StaffMember
from app.identity.schemas_staff import StaffOut, StaffPatchIn, StaffPath
from app.identity.session import current_staff
from app.identity.staff_service import all_clinics_of_organization, dedupe, list_staff
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response

api = APIBlueprint("staff_update", __name__, abp_tags=[Tag(name="staff")], abp_responses=VALIDATION_ERROR_RESPONSES)


@api.patch(
    "/api/staff/<uuid:staff_id>",
    responses={200: StaffOut, 401: ErrorResponse, 403: ErrorResponse, 404: ErrorResponse, 409: ErrorResponse},
)
@login_required
@require_role(Role.CLINIC_MANAGER)
def update_staff(path: StaffPath, body: StaffPatchIn):
    """Change a Staff Member's name, Roles, Clinics or active flag; never the last active Clinic Manager."""
    db = get_session()
    me = current_staff()
    org = me.organization_id
    fields = [f for f in ("full_name", "roles", "clinic_ids", "is_active") if getattr(body, f) is not None]
    if not fields:
        return error_response(422, "validation_error", fields=["body"])
    if body.clinic_ids is not None and not all_clinics_of_organization(db, org, body.clinic_ids):
        return error_response(422, "validation_error", fields=["clinic_ids"])

    managers = set(
        db.scalars(
            select(StaffMember.id)
            .where(
                StaffMember.organization_id == org,
                StaffMember.is_active.is_(True),
                Role.CLINIC_MANAGER == any_(StaffMember.roles),
            )
            .order_by(StaffMember.id)
            .with_for_update()
        )
    )
    target = db.scalar(
        select(StaffMember)
        .where(StaffMember.id == path.staff_id, StaffMember.organization_id == org)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if target is None:
        raise ApiError(404, "not_found")

    new_roles = dedupe(body.roles) if body.roles is not None else list(target.roles)
    new_active = body.is_active if body.is_active is not None else target.is_active
    was_manager = target.id in managers
    stays_manager = new_active and Role.CLINIC_MANAGER in new_roles
    if was_manager and not stays_manager and not (managers - {target.id}):
        raise ApiError(409, "last_manager")

    if body.full_name is not None:
        target.full_name = body.full_name
    target.roles = new_roles
    target.is_active = new_active
    db.flush()
    if body.clinic_ids is not None:
        db.execute(delete(StaffClinic).where(StaffClinic.staff_member_id == target.id))
        db.add_all(
            StaffClinic(organization_id=org, staff_member_id=target.id, clinic_id=cid)
            for cid in dedupe(body.clinic_ids)
        )
        db.flush()
    record_audit(
        db,
        organization_id=org,
        action=AuditAction.UPDATE,
        entity_type="staff_member",
        entity_id=target.id,
        staff_member_id=me.id,
        account_id=me.account_id,
        detail={"fields": fields},
    )
    [out] = list_staff(db, org, target.id)
    return out.model_dump(mode="json")
