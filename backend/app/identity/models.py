from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CHAR,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.identity.core.roles import Role
from app.platform.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="Europe/Zagreb", server_default="Europe/Zagreb")
    currency: Mapped[str] = mapped_column(Text, default="EUR", server_default="EUR")
    locale: Mapped[str] = mapped_column(Text, default="en", server_default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class Account(Base):

    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, default=None)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger, default=None)
    credentials_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class StaffClinic(Base):
    __tablename__ = "staff_clinics"

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    staff_member_id: Mapped[UUID] = mapped_column(ForeignKey("staff_members.id"), primary_key=True)
    clinic_id: Mapped[UUID] = mapped_column(ForeignKey("clinics.id"), primary_key=True, index=True)


class StaffMember(Base):
    __tablename__ = "staff_members"
    __table_args__ = (
        UniqueConstraint("account_id", "organization_id"),
        CheckConstraint("cardinality(roles) >= 1", name="ck_staff_members_roles_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    full_name: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[Role]] = mapped_column(
        ARRAY(
            Enum(
                Role,
                name="staff_role",
                values_callable=lambda e: [m.value for m in e],
                create_type=False,
            )
        )
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )

    account: Mapped[Account] = relationship()
    clinics: Mapped[list[Clinic]] = relationship(secondary="staff_clinics", viewonly=True)


class Invitation(Base):

    __tablename__ = "invitations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(CITEXT)
    full_name: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[Role]] = mapped_column(
        ARRAY(
            Enum(
                Role,
                name="staff_role",
                values_callable=lambda e: [m.value for m in e],
                create_type=False,
            )
        )
    )
    clinic_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)))
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_staff_member_id: Mapped[UUID] = mapped_column()
    accepted_staff_member_id: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
