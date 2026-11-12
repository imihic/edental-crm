from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel
from sqlalchemy import select

from app.identity.core.permissions import requires_totp
from app.identity.guards import login_required
from app.identity.lookup import list_memberships
from app.identity.models import Account, Clinic, Organization
from app.identity.session import current_staff
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "auth_me", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class AccountOut(BaseModel):
    id: str
    email: str


class SessionStaffOut(BaseModel):
    id: str
    full_name: str
    roles: list[str]


class OrganizationDetailOut(BaseModel):
    id: str
    name: str
    timezone: str
    currency: str
    locale: str


class ClinicOut(BaseModel):
    id: str
    name: str


class MeResponse(BaseModel):
    account: AccountOut
    staff: SessionStaffOut
    organization: OrganizationDetailOut
    clinics: list[ClinicOut]
    organization_clinics: list[ClinicOut]
    organizations_count: int
    totp_enrollment_required: bool


@api.get("/api/auth/me", responses={200: MeResponse, 401: ErrorResponse})
@login_required
def me():
    staff = current_staff()
    db = get_session()
    account = db.get(Account, staff.account_id)
    org = db.get(Organization, staff.organization_id)
    organization_clinics = db.execute(
        select(Clinic.id, Clinic.name)
        .where(Clinic.organization_id == staff.organization_id)
        .order_by(Clinic.name, Clinic.id)
    ).all()
    return {
        "account": {"id": str(account.id), "email": account.email},
        "staff": {"id": str(staff.id), "full_name": staff.full_name, "roles": [r.value for r in staff.roles]},
        "organization": {
            "id": str(org.id),
            "name": org.name,
            "timezone": org.timezone,
            "currency": org.currency,
            "locale": org.locale,
        },
        "clinics": [
            {"id": str(c.id), "name": c.name} for c in sorted(staff.clinics, key=lambda c: (c.name, str(c.id)))
        ],
        "organization_clinics": [
            {"id": str(clinic_id), "name": name} for clinic_id, name in organization_clinics
        ],
        "organizations_count": len(list_memberships(db, staff.account_id)),
        "totp_enrollment_required": requires_totp(staff.roles) and not account.totp_enabled,
    }
