from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.models import Enquiry
from app.people.patient_service import clinic_name, load_patient, merged_response, validation_failed
from app.people.schemas import EnquiryIn, EnquiryOut, MergedResponse, PatientPath, enquiry_out
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "patient_enquiry_create", __name__, abp_tags=[Tag(name="patients")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class PatientEnquiryHistoryQuery(BaseModel):
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=25, ge=1, le=100)


class PatientEnquiryHistory(BaseModel):
    items: list[EnquiryOut]
    total: int


@api.get(
    "/api/patients/<uuid:patient_id>/enquiries",
    responses={200: PatientEnquiryHistory, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse},
)
@login_required
def get_patient_enquiries(path: PatientPath, query: PatientEnquiryHistoryQuery):
    """List a Patient's Enquiries, including those carried over during conversion, newest first."""
    db = get_session()
    staff = current_staff()
    patient = load_patient(db, path.patient_id)
    if patient.retired_at is not None:
        return merged_response(patient)
    filters = (Enquiry.organization_id == staff.organization_id, Enquiry.patient_id == patient.id)
    total = db.scalar(select(func.count()).select_from(Enquiry).where(*filters))
    enquiries = db.scalars(
        select(Enquiry)
        .where(*filters)
        .order_by(Enquiry.received_at.desc(), Enquiry.id.desc())
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    ).all()
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.VIEW,
        entity_type="patient",
        entity_id=patient.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
        detail={"field": "enquiries"},
    )
    return PatientEnquiryHistory(items=[enquiry_out(enquiry) for enquiry in enquiries], total=total).model_dump(mode="json")


@api.post(
    "/api/patients/<uuid:patient_id>/enquiries",
    responses={201: EnquiryOut, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse},
)
@login_required
def create_patient_enquiry(path: PatientPath, body: EnquiryIn):
    """Record an Enquiry from an existing Patient (no Lead is created). Audited `create` on `enquiry`."""
    db = get_session()
    staff = current_staff()
    patient = load_patient(db, path.patient_id)
    if patient.retired_at is not None:
        return merged_response(patient)
    if clinic_name(db, body.clinic_id) is None:
        return validation_failed(["clinic_id"])
    enquiry = Enquiry(
        organization_id=staff.organization_id,
        patient_id=patient.id,
        clinic_id=body.clinic_id,
        source=body.source,
        message=body.message,
        preferred_contact_time=body.preferred_contact_time,
        created_by_staff_member_id=staff.id,
    )
    db.add(enquiry)
    db.flush()
    db.refresh(enquiry)
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.CREATE,
        entity_type="enquiry",
        entity_id=enquiry.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
    )
    return enquiry_out(enquiry).model_dump(mode="json"), 201
