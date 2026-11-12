from uuid import UUID

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel

from app.identity.lookup import list_memberships
from app.identity.schemas import OkResponse, OrganizationsResponse
from app.identity.session import bind_staff_member, current_account_id
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse

api = APIBlueprint(
    "auth_organizations", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class ChooseOrganizationBody(BaseModel):
    organization_id: UUID


@api.get("/api/auth/organizations", responses={200: OrganizationsResponse, 401: ErrorResponse})
def list_organizations():
    memberships = list_memberships(get_session(), current_account_id())
    return {"organizations": [{"id": str(m.organization_id), "name": m.organization_name} for m in memberships]}


@api.post(
    "/api/auth/organization",
    responses={200: OkResponse, 401: ErrorResponse, 403: ErrorResponse},
)
def choose_organization(body: ChooseOrganizationBody):
    """Bind the session to one of the Account's Organizations (also used to switch)."""
    account_id = current_account_id()
    memberships = list_memberships(get_session(), account_id)
    membership = next((m for m in memberships if m.organization_id == body.organization_id), None)
    if membership is None:
        raise ApiError(403, "forbidden")
    bind_staff_member(account_id, membership)
    return {"status": "ok"}
