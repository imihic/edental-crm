from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import select

from app.compliance import AuditAction, record_audit
from app.identity import current_staff, login_required
from app.people.consent_service import consent_history, consent_out, current_consent
from app.people.lead_service import load_lead, merged_lead_response
from app.people.models import Consent, GuardianLink
from app.people.patient_service import is_minor, load_patient, merged_response, validation_failed
from app.people.schemas import ConsentIn, ConsentOut, ConsentsResponse, LeadConvertedResponse, LeadPath, MergedResponse, PatientPath
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse, error_response

api = APIBlueprint("consents", __name__, abp_tags=[Tag(name="consents")], abp_responses=VALIDATION_ERROR_RESPONSES)

READ_RESPONSES = {200: ConsentsResponse, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse}
WRITE_RESPONSES = {201: ConsentOut, 401: ErrorResponse, 404: ErrorResponse, 410: MergedResponse}
LEAD_WRITE_RESPONSES = {**WRITE_RESPONSES, 409: LeadConvertedResponse}


def _record(db, staff, body: ConsentIn, *, subject: str, patient_id=None, lead_id=None, guardian_link_id=None):
    entry = Consent(
        organization_id=staff.organization_id,
        patient_id=patient_id,
        lead_id=lead_id,
        purpose=body.purpose,
        granted=body.granted,
        source=body.source,
        given_by_guardian_link_id=guardian_link_id,
        recorded_by_staff_member_id=staff.id,
    )
    db.add(entry)
    db.flush()
    db.refresh(entry)
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.CREATE,
        entity_type="consent",
        entity_id=entry.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
        detail={"subject": subject, "purpose": body.purpose, "granted": body.granted},
    )
    return consent_out(entry).model_dump(mode="json"), 201


@api.get("/api/patients/<uuid:patient_id>/consents", responses=READ_RESPONSES)
@login_required
def get_patient_consents(path: PatientPath):
    """A Patient's Consent history (newest first) and the current state per purpose."""
    db = get_session()
    patient = load_patient(db, path.patient_id)
    if patient.retired_at is not None:
        return merged_response(patient)
    history = consent_history(db, patient_id=patient.id)
    return ConsentsResponse(
        current=current_consent(db, patient_id=patient.id), history=[consent_out(c) for c in history]
    ).model_dump(mode="json")


@api.post("/api/patients/<uuid:patient_id>/consents", responses=WRITE_RESPONSES)
@login_required
def add_patient_consent(path: PatientPath, body: ConsentIn):
    """Record a Consent entry (a withdrawal is a new entry). A minor needs the Guardian link who gave it."""
    db = get_session()
    staff = current_staff()
    link_id = body.given_by_guardian_link_id
    patient = load_patient(db, path.patient_id, for_update=True)
    if patient.retired_at is not None:
        return merged_response(patient)
    if link_id is not None:
        active_link_id = db.scalar(
            select(GuardianLink.id)
            .where(GuardianLink.id == link_id, GuardianLink.patient_id == patient.id, GuardianLink.ended_at.is_(None))
            .with_for_update(read=True)
        )
        if active_link_id is None:
            return validation_failed(["given_by_guardian_link_id"])
    elif is_minor(patient):
        return validation_failed(["given_by_guardian_link_id"])
    return _record(db, staff, body, subject="patient", patient_id=patient.id, guardian_link_id=link_id)


@api.get("/api/leads/<uuid:lead_id>/consents", responses=READ_RESPONSES)
@login_required
def get_lead_consents(path: LeadPath):
    """A Lead's Consent history (newest first) and the current state per purpose."""
    db = get_session()
    lead = load_lead(db, path.lead_id)
    if lead.retired_at is not None:
        return merged_lead_response(lead)
    history = consent_history(db, lead_id=lead.id)
    return ConsentsResponse(
        current=current_consent(db, lead_id=lead.id), history=[consent_out(c) for c in history]
    ).model_dump(mode="json")


@api.post("/api/leads/<uuid:lead_id>/consents", responses=LEAD_WRITE_RESPONSES)
@login_required
def add_lead_consent(path: LeadPath, body: ConsentIn):
    """Record a Consent entry for a Lead. Leads have no date of birth, so no Guardian rules apply.

    A Lead that is (or just became) converted answers 409 `lead_converted` with the new `patient_id`:
    record the Consent on the Patient instead.
    """
    db = get_session()
    staff = current_staff()
    lead = load_lead(db, path.lead_id, for_update=True)
    if lead.retired_at is not None:
        return merged_lead_response(lead)
    if lead.stage == "converted":
        return error_response(409, "lead_converted", patient_id=str(lead.converted_patient_id))
    return _record(db, staff, body, subject="lead", lead_id=lead.id)
