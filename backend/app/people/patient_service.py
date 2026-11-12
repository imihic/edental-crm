from datetime import date
from uuid import UUID

from flask import jsonify
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.compliance import AuditAction, record_audit
from app.people.consent_service import current_consent
from app.people.core.duplicates import Candidate
from app.people.core.oib import is_valid_oib
from app.people.core.phones import InvalidPhone, normalize_phone
from app.people.duplicates import find_possible_duplicates
from app.people.guardian_service import guardian_of_list, guardians_of
from app.people.models import Patient
from app.people.schemas import ADULT_AGE, PatientCreate, PatientDetail, age_on, summary_of
from app.platform.errors import ApiError, error_response


def load_patient(
    session: Session, patient_id: UUID, *, for_key_share: bool = False, for_update: bool = False
) -> Patient:
    if for_update:
        patient = session.scalars(
            select(Patient).where(Patient.id == patient_id).with_for_update().execution_options(populate_existing=True)
        ).one_or_none()
    else:
        patient = session.get(
            Patient, patient_id, with_for_update={"read": True, "key_share": True} if for_key_share else None
        )
    if patient is None:
        raise ApiError(404, "not_found")
    return patient


def merged_response(patient: Patient):
    return error_response(410, "merged", merged_into=str(patient.retired_into_patient_id))


def validation_failed(fields: list[str]):
    return error_response(422, "validation_error", fields=fields)


def clinic_name(session: Session, clinic_id: UUID) -> str | None:
    return session.execute(text("SELECT name FROM clinics WHERE id = :id"), {"id": clinic_id}).scalar_one_or_none()


def clean_fields(session: Session, data: dict) -> tuple[dict, list[str]]:
    clean, bad = {}, []
    for key, value in data.items():
        if isinstance(value, str) and key not in ("first_name", "last_name", "preferred_language"):
            value = value.strip() or None
        if key == "oib" and value is not None and not is_valid_oib(value):
            bad.append(key)
        elif key == "phone" and value is not None:
            try:
                value = normalize_phone(value)
            except InvalidPhone:
                bad.append(key)
        elif key == "preferred_clinic_id" and value is not None and clinic_name(session, value) is None:
            bad.append(key)
        clean["phone_e164" if key == "phone" else key] = value
    return clean, bad


OIB_UNIQUE_INDEX = "uq_patients_org_oib"


def is_oib_conflict(exc: IntegrityError) -> bool:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == OIB_UNIQUE_INDEX


def oib_taken(session: Session, oib: str, *, except_id: UUID | None = None) -> bool:
    query = select(Patient.id).where(Patient.oib == oib, Patient.retired_at.is_(None))
    if except_id is not None:
        query = query.where(Patient.id != except_id)
    return session.scalar(query.limit(1)) is not None


def age_of(p: Patient) -> int | None:
    return age_on(p.date_of_birth, date.today()) if p.date_of_birth else None


def is_minor(p: Patient) -> bool:
    age = age_of(p)
    return age is not None and age < ADULT_AGE


def detail_of(session: Session, p: Patient) -> dict:
    age = age_of(p)
    name = clinic_name(session, p.preferred_clinic_id) if p.preferred_clinic_id else None
    return PatientDetail(
        **summary_of(p),
        address=p.address,
        notes=p.notes,
        preferred_clinic={"id": p.preferred_clinic_id, "name": name} if name is not None else None,
        preferred_language=p.preferred_language,
        guardians=guardians_of(session, p.id),
        guardian_of=guardian_of_list(session, p.id),
        age=age,
        is_minor=is_minor(p),
        consent=current_consent(session, patient_id=p.id),
        created_at=p.created_at,
        updated_at=p.updated_at,
    ).model_dump(mode="json")


def create_patient_record(
    session: Session, staff, body: PatientCreate, *, exclude_lead_id: UUID | None = None
) -> tuple[Patient | None, object | None]:
    clean, bad = clean_fields(session, body.model_dump(exclude={"confirm_duplicates"}))
    if bad:
        return None, validation_failed(bad)
    if clean["oib"] and oib_taken(session, clean["oib"]):
        return None, error_response(409, "oib_taken")
    if not body.confirm_duplicates:
        candidate = Candidate(
            clean["first_name"], clean["last_name"], clean["date_of_birth"], clean["email"], clean["oib"]
        )
        duplicates = find_possible_duplicates(session, candidate, exclude_lead_id=exclude_lead_id)
        if duplicates:
            response = jsonify(
                {"error": "possible_duplicates", "duplicates": [d.model_dump(mode="json") for d in duplicates]}
            )
            response.status_code = 409
            return None, response
    patient = Patient(organization_id=staff.organization_id, **clean)
    try:
        with session.begin_nested():
            session.add(patient)
    except IntegrityError as exc:
        if not is_oib_conflict(exc):
            raise
        return None, error_response(409, "oib_taken")
    session.refresh(patient)
    record_audit(
        session,
        organization_id=staff.organization_id,
        action=AuditAction.CREATE,
        entity_type="patient",
        entity_id=patient.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
    )
    return patient, None
