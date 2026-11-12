from flask_openapi3 import APIBlueprint, Tag

from app.identity.core.roles import Role
from app.identity.guards import login_required, require_role
from app.identity.schemas_staff import StaffListOut
from app.identity.session import current_staff
from app.identity.staff_service import list_staff
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint("staff_list", __name__, abp_tags=[Tag(name="staff")], abp_responses=VALIDATION_ERROR_RESPONSES)


@api.get("/api/staff", responses={200: StaffListOut, 401: ErrorResponse, 403: ErrorResponse})
@login_required
@require_role(Role.CLINIC_MANAGER)
def get_staff():
    """Every Staff Member of the Organization, active or not, with e-mail, Roles and Clinics."""
    items = list_staff(get_session(), current_staff().organization_id)
    return StaffListOut(items=items).model_dump(mode="json")
