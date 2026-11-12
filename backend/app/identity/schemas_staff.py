from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.identity.core.roles import Role


class ClinicRefOut(BaseModel):
    id: UUID
    name: str


class StaffOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    roles: list[Role]
    clinics: list[ClinicRefOut]
    is_active: bool


class StaffListOut(BaseModel):
    items: list[StaffOut]


class StaffPath(BaseModel):
    staff_id: UUID


class StaffPatchIn(BaseModel):
    """Only these fields may change; the e-mail and the Account are not editable here."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    roles: list[Role] | None = Field(default=None, min_length=1)
    clinic_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("blank")
        return v.strip()


class InvitationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    roles: list[Role] = Field(min_length=1)
    clinic_ids: list[UUID] = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        local, _, domain = v.partition("@")
        if not local or "." not in domain or any(c.isspace() for c in v) or "@" in domain:
            raise ValueError("email")
        return v

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("blank")
        return v.strip()


class InvitationCreatedOut(BaseModel):
    id: UUID
    url: str
    expires_at: datetime


class InvitationItemOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    roles: list[Role]
    clinic_ids: list[UUID]
    expires_at: datetime
    created_at: datetime


class InvitationListOut(BaseModel):
    items: list[InvitationItemOut]


class InvitationPath(BaseModel):
    invitation_id: UUID


class InvitationTokenPath(BaseModel):
    token: str


class PublicInvitationOut(BaseModel):
    organization_name: str
    email: str
    full_name: str
    account_exists: bool


class AcceptInvitationIn(BaseModel):
    password: str = Field(max_length=1024)
    code: str | None = Field(default=None, max_length=16)


class AcceptedOut(BaseModel):
    status: Literal["accepted"]
