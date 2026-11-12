from uuid import UUID

from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.core.oib import is_valid_oib
from app.people.models import Patient
from app.people.patient_service import validation_failed
from app.people.schemas import PatientListResponse, PatientSummary, summary_of
from app.people.search import search_predicate
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "patients_list", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class ListQuery(BaseModel):
    q: str = Field(default="", max_length=100)
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=25, ge=1, le=100)


class PatientOibLookupIn(BaseModel):
    oib: str = Field(pattern=r"^[0-9]{11}$")


class PatientOibLookupOut(BaseModel):
    patient_id: UUID | None


@api.post("/api/patients/lookup-oib", responses={200: PatientOibLookupOut, 401: ErrorResponse})
@login_required
def lookup_patient_by_oib(body: PatientOibLookupIn):
    """Return only the active Patient's ID for an exact OIB in the current Organization."""
    if not is_valid_oib(body.oib):
        return validation_failed(["oib"])
    db = get_session()
    staff = current_staff()
    patient_id = db.scalar(
        select(Patient.id).where(
            Patient.organization_id == staff.organization_id, Patient.oib == body.oib, Patient.retired_at.is_(None),
        )
    )
    if patient_id is not None:
        record_audit(
            db,
            organization_id=staff.organization_id,
            action=AuditAction.VIEW,
            entity_type="patient",
            entity_id=patient_id,
            staff_member_id=staff.id,
            account_id=staff.account_id,
            detail={"field": "oib", "operation": "lookup"},
        )
    return PatientOibLookupOut(patient_id=patient_id).model_dump(mode="json"), 200, {"Cache-Control": "no-store"}


@api.get("/api/patients", responses={200: PatientListResponse, 401: ErrorResponse})
@login_required
def list_patients(query: ListQuery):
    """Search Patients (diacritic-insensitive, typo-tolerant, phone in any format); not audited."""
    filters = [Patient.retired_at.is_(None)]
    match = search_predicate(Patient, query.q)
    if match is not None:
        filters.append(match)
    db = get_session()
    total = db.scalar(select(func.count()).select_from(Patient).where(*filters))
    rows = db.scalars(
        select(Patient)
        .where(*filters)
        .order_by(Patient.last_name, Patient.first_name, Patient.id)
        .limit(query.page_size)
        .offset((query.page - 1) * query.page_size)
    ).all()
    return PatientListResponse(
        items=[PatientSummary(**summary_of(p)) for p in rows], total=total
    ).model_dump(mode="json")
