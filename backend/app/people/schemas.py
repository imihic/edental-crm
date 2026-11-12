import re
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.people.core.names import normalize_name
from app.people.core.oib import mask_oib
from app.people.models import Enquiry, Lead, Patient

EDITABLE_FIELDS = (
    "first_name",
    "last_name",
    "date_of_birth",
    "phone",
    "email",
    "oib",
    "address",
    "notes",
    "preferred_clinic_id",
    "preferred_language",
)
ADULT_AGE = 18
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")


def _check_email(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not _EMAIL.match(value):
        raise ValueError("invalid email")
    return value


def _check_message(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("blank")
    return value


def _check_birth_date(value: date | None) -> date | None:
    if value is not None and value > date.today():
        raise ValueError("in the future")
    return value


class PatientIn(BaseModel):
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    oib: str | None = Field(default=None, max_length=11)
    address: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=500)
    preferred_clinic_id: UUID | None = None
    preferred_language: Literal["hr", "en"] = "en"

    @field_validator("first_name", "last_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = normalize_name(value)
        if not value:
            raise ValueError("blank")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return _check_email(value)

    @field_validator("date_of_birth")
    @classmethod
    def _birth_date(cls, value: date | None) -> date | None:
        return _check_birth_date(value)


class PatientCreate(PatientIn):
    confirm_duplicates: bool = False


class PatientPatch(BaseModel):
    """Partial PatientIn: only the keys sent are changed (null clears an optional field)."""

    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    oib: str | None = Field(default=None, max_length=11)
    address: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=500)
    preferred_clinic_id: UUID | None = None
    preferred_language: Literal["hr", "en"] | None = None

    @field_validator("first_name", "last_name")
    @classmethod
    def _name(cls, value: str | None) -> str:
        if value is None or not normalize_name(value):
            raise ValueError("required")
        return normalize_name(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return _check_email(value)

    @field_validator("date_of_birth")
    @classmethod
    def _birth_date(cls, value: date | None) -> date | None:
        return _check_birth_date(value)

    @field_validator("preferred_language")
    @classmethod
    def _language(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("required")
        return value


class PatientPath(BaseModel):
    patient_id: UUID


class PatientSummary(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    date_of_birth: date | None
    phone: str | None
    email: str | None
    oib_masked: str | None


class PatientListResponse(BaseModel):
    items: list[PatientSummary]
    total: int


class PreferredClinicOut(BaseModel):
    id: UUID
    name: str


class GuardianOut(BaseModel):
    id: UUID
    relationship: Literal["parent", "legal_guardian", "other"]
    kind: Literal["patient", "contact"]
    guardian_id: UUID
    display_name: str
    phone: str | None
    email: str | None


class GuardianOfOut(BaseModel):
    patient_id: UUID
    display_name: str


class ContactIn(BaseModel):
    full_name: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = normalize_name(value)
        if not value:
            raise ValueError("blank")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return _check_email(value)


class GuardianIn(BaseModel):
    """Either an existing Patient (`guardian_patient_id`) or a new Contact (`contact`)."""

    relationship: Literal["parent", "legal_guardian", "other"]
    guardian_patient_id: UUID | None = None
    contact: ContactIn | None = None


class GuardianPath(BaseModel):
    patient_id: UUID
    link_id: UUID


class ContactPath(BaseModel):
    contact_id: UUID


ConsentState = Literal["granted", "withdrawn", "unknown"]


class PatientDetail(PatientSummary):
    address: str | None
    notes: str | None
    preferred_clinic: PreferredClinicOut | None
    preferred_language: str
    guardians: list[GuardianOut]
    guardian_of: list[GuardianOfOut]
    age: int | None
    is_minor: bool
    consent: dict[str, ConsentState]
    created_at: datetime
    updated_at: datetime


class DuplicateOut(BaseModel):
    kind: Literal["patient", "lead"]
    id: UUID
    display_name: str
    reasons: list[str]


class ConflictResponse(BaseModel):
    """409: `possible_duplicates` (with the matches) or `oib_taken`."""

    error: str
    duplicates: list[DuplicateOut] | None = None


class MergedResponse(BaseModel):
    error: str
    merged_into: UUID


class LeadConvertedResponse(BaseModel):
    error: str
    patient_id: UUID


class RevealOibResponse(BaseModel):
    oib: str | None


LeadStage = Literal["new", "contacted", "consultation_booked", "converted", "lost"]
LostReason = Literal["price", "distance", "chose_other_clinic", "no_response", "not_needed", "other"]
StaffEnquirySource = Literal["phone", "walk_in", "email", "other"]
EnquirySource = Literal["website_form", "phone", "walk_in", "email", "other"]


class LeadCreate(BaseModel):
    full_name: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    clinic_id: UUID
    source: StaffEnquirySource
    message: str = Field(max_length=2000)
    preferred_contact_time: str | None = Field(default=None, max_length=100)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = normalize_name(value)
        if not value:
            raise ValueError("blank")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return _check_email(value)

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        return _check_message(value)

    @field_validator("preferred_contact_time")
    @classmethod
    def _contact_time(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class LeadCreated(BaseModel):
    attached_to: Literal["lead", "patient"]
    lead_id: UUID | None = None
    patient_id: UUID | None = None


class LeadPath(BaseModel):
    lead_id: UUID


class LeadStageIn(BaseModel):
    stage: LeadStage
    lost_reason: LostReason | None = None
    lost_note: str | None = Field(default=None, max_length=500)


class LeadSummary(BaseModel):
    id: UUID
    full_name: str
    phone: str | None
    email: str | None
    clinic_id: UUID
    stage: LeadStage
    lost_reason: LostReason | None
    created_at: datetime


class LeadListResponse(BaseModel):
    items: list[LeadSummary]
    total: int
    counts: dict[str, int]


class EnquiryOut(BaseModel):
    id: UUID
    lead_id: UUID | None
    patient_id: UUID | None
    clinic_id: UUID
    source: EnquirySource
    message: str
    preferred_contact_time: str | None
    marketing_consent_requested: bool
    received_at: datetime


class LeadDetail(LeadSummary):
    lost_note: str | None
    converted_patient_id: UUID | None
    updated_at: datetime
    enquiries: list[EnquiryOut]
    possible_duplicates: list[DuplicateOut]
    consent: dict[str, ConsentState]


class EnquiryIn(BaseModel):
    clinic_id: UUID
    source: StaffEnquirySource
    message: str = Field(max_length=2000)
    preferred_contact_time: str | None = Field(default=None, max_length=100)

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        return _check_message(value)

    @field_validator("preferred_contact_time")
    @classmethod
    def _contact_time(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


def enquiry_out(e: Enquiry) -> EnquiryOut:
    return EnquiryOut(
        id=e.id,
        lead_id=e.lead_id,
        patient_id=e.patient_id,
        clinic_id=e.clinic_id,
        source=e.source,
        message=e.message,
        preferred_contact_time=e.preferred_contact_time,
        marketing_consent_requested=e.marketing_consent_requested,
        received_at=e.received_at,
    )


def lead_summary_of(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "full_name": lead.full_name,
        "phone": lead.phone_e164,
        "email": lead.email,
        "clinic_id": lead.clinic_id,
        "stage": lead.stage,
        "lost_reason": lead.lost_reason,
        "created_at": lead.created_at,
    }


def summary_of(p: Patient) -> dict:
    return {
        "id": p.id,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "date_of_birth": p.date_of_birth,
        "phone": p.phone_e164,
        "email": p.email,
        "oib_masked": mask_oib(p.oib) if p.oib else None,
    }


def age_on(born: date, today: date) -> int:
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class ConsentIn(BaseModel):
    purpose: Literal["marketing"]
    granted: bool
    source: Literal["form", "paper", "verbal"]
    given_by_guardian_link_id: UUID | None = None


class ConsentOut(BaseModel):
    id: UUID
    purpose: str
    granted: bool
    source: str
    given_by_guardian_link_id: UUID | None
    carried_from_consent_id: UUID | None
    recorded_by_staff_member_id: UUID | None
    recorded_at: datetime


class ConsentsResponse(BaseModel):
    current: dict[str, ConsentState]
    history: list[ConsentOut]


class ClinicPath(BaseModel):
    clinic_id: UUID


class EnquiryFormOut(BaseModel):
    key: str
    path: str
    enabled: bool


class PublicFormPath(BaseModel):
    key: str


class PublicFormInfo(BaseModel):
    clinic_name: str
    organization_name: str
    locale: str


class PublicEnquiryIn(BaseModel):
    full_name: str = Field(max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    message: str = Field(max_length=2000)
    preferred_contact_time: str | None = Field(default=None, max_length=100)
    marketing_consent: bool
    website: str = Field(default="", max_length=2000)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = normalize_name(value)
        if not value:
            raise ValueError("blank")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return _check_email(value)

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        return _check_message(value)

    @field_validator("preferred_contact_time")
    @classmethod
    def _contact_time(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class PublicEnquiryReceived(BaseModel):
    status: Literal["received"]
