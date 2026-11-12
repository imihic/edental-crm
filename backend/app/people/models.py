from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import CHAR, Boolean, Computed, Date, DateTime, Text, func, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date, default=None)
    phone_e164: Mapped[str | None] = mapped_column(Text, default=None)
    email: Mapped[str | None] = mapped_column(CITEXT, default=None)
    oib: Mapped[str | None] = mapped_column(CHAR(11), default=None)
    address: Mapped[str | None] = mapped_column(Text, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    preferred_clinic_id: Mapped[UUID | None] = mapped_column(default=None)
    preferred_language: Mapped[str] = mapped_column(Text, default="en", server_default="en")
    retired_into_patient_id: Mapped[UUID | None] = mapped_column(default=None)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    import_id: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )
    search_text: Mapped[str] = mapped_column(
        Text,
        Computed(
            "f_unaccent(lower(first_name || ' ' || last_name || ' ' || coalesce(email,'') "
            "|| ' ' || coalesce(phone_e164,'') || ' ' || coalesce(oib,'')))",
            persisted=True,
        ),
    )


class Contact(Base):

    __tablename__ = "contacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    full_name: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(Text, default=None)
    email: Mapped[str | None] = mapped_column(CITEXT, default=None)
    promoted_to_patient_id: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class GuardianLink(Base):

    __tablename__ = "guardian_links"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    guardian_patient_id: Mapped[UUID | None] = mapped_column(default=None)
    guardian_contact_id: Mapped[UUID | None] = mapped_column(default=None)
    relationship: Mapped[str] = mapped_column(Text)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class Lead(Base):

    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    full_name: Mapped[str] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(Text, default=None)
    email: Mapped[str | None] = mapped_column(CITEXT, default=None)
    clinic_id: Mapped[UUID]
    stage: Mapped[str] = mapped_column(Text, default="new", server_default="new")
    lost_reason: Mapped[str | None] = mapped_column(Text, default=None)
    lost_note: Mapped[str | None] = mapped_column(Text, default=None)
    converted_patient_id: Mapped[UUID | None] = mapped_column(default=None)
    retired_into_patient_id: Mapped[UUID | None] = mapped_column(default=None)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )
    search_text: Mapped[str] = mapped_column(
        Text,
        Computed(
            "f_unaccent(lower(full_name || ' ' || coalesce(email,'') || ' ' || coalesce(phone_e164,'')))",
            persisted=True,
        ),
    )


class Enquiry(Base):

    __tablename__ = "enquiries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    lead_id: Mapped[UUID | None] = mapped_column(default=None)
    patient_id: Mapped[UUID | None] = mapped_column(default=None)
    clinic_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    preferred_contact_time: Mapped[str | None] = mapped_column(Text, default=None)
    marketing_consent_requested: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    created_by_staff_member_id: Mapped[UUID | None] = mapped_column(default=None)


class Consent(Base):

    __tablename__ = "consents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    patient_id: Mapped[UUID | None] = mapped_column(default=None)
    lead_id: Mapped[UUID | None] = mapped_column(default=None)
    purpose: Mapped[str] = mapped_column(Text)
    granted: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(Text)
    given_by_guardian_link_id: Mapped[UUID | None] = mapped_column(default=None)
    carried_from_consent_id: Mapped[UUID | None] = mapped_column(default=None)
    recorded_by_staff_member_id: Mapped[UUID | None] = mapped_column(default=None)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )


class PatientImport(Base):

    __tablename__ = "patient_imports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID]
    filename: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="previewed", server_default="previewed")
    rows: Mapped[list] = mapped_column(JSONB)
    created_by_staff_member_id: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now()
    )
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    counts: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
