from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, ForeignKeyConstraint, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base


class AuditAction(StrEnum):
    VIEW = "view"
    EXPORT = "export"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"


def _now() -> datetime:
    return datetime.now(UTC)


class AuditEntry(Base):

    __tablename__ = "audit_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "staff_member_id"],
            ["staff_members.organization_id", "staff_members.id"],
        ),
        Index("ix_audit_entries_organization_id_occurred_at", "organization_id", "occurred_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"))
    staff_member_id: Mapped[UUID | None] = mapped_column(default=None)
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"), default=None)
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, native_enum=False, create_constraint=False, length=32,
             values_callable=lambda e: [m.value for m in e])
    )
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[UUID | None] = mapped_column(default=None)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
