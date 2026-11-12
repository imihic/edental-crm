from datetime import UTC, date, datetime

from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.compliance import AuditAction, record_audit
from app.identity import Role, current_staff, login_required, require_role
from app.people.import_service import CommitIn, CommitOut, ImportPath, blank_expired, is_expired
from app.people.models import Patient, PatientImport
from app.people.patient_service import clean_fields, is_oib_conflict
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response

api = APIBlueprint(
    "import_commit", __name__, abp_tags=[Tag(name="imports")], abp_responses=VALIDATION_ERROR_RESPONSES
)


def _kept(record: dict) -> dict:
    return {k: record.get(k) for k in ("line", "status", "errors", "in_file_duplicate_of_line")}


def _wanted(record: dict, include_duplicates: bool) -> bool:
    if record["status"] == "valid":
        return True
    return record["status"] == "duplicate" and include_duplicates and not record["oib_conflict"]


@api.post(
    "/api/imports/patients/<uuid:import_id>/commit",
    responses={
        200: CommitOut,
        401: ErrorResponse,
        403: ErrorResponse,
        404: ErrorResponse,
        409: ErrorResponse,
        410: ErrorResponse,
    },
)
@login_required
@require_role(Role.CLINIC_MANAGER)
def commit_import(path: ImportPath, body: CommitIn):
    """Create Patients from the previewed rows in one transaction (no Consent is recorded).

    Rows whose OIB is taken by now are skipped, not failed. Audited with counts only.
    """
    db = get_session()
    staff = current_staff()
    blank_expired(db)
    imp = db.scalar(select(PatientImport).where(PatientImport.id == path.import_id).with_for_update())
    if imp is None:
        raise ApiError(404, "not_found")
    if imp.status == "committed":
        raise ApiError(409, "already_committed")
    if is_expired(imp):
        imp.status = "expired"
        imp.rows = [_kept(r) for r in imp.rows]
        return error_response(410, "import_expired")

    created = 0
    for record in imp.rows:
        if not _wanted(record, body.include_duplicates):
            continue
        v = record["values"]
        clean, bad = clean_fields(
            db,
            {
                "first_name": v["first_name"],
                "last_name": v["last_name"],
                "date_of_birth": date.fromisoformat(v["date_of_birth"]) if v["date_of_birth"] else None,
                "phone": v["phone"],
                "email": v["email"],
                "oib": v["oib"],
                "address": v["address"],
                "notes": v["notes"],
            },
        )
        if bad:
            continue
        patient = Patient(
            organization_id=staff.organization_id,
            import_id=imp.id,
            preferred_clinic_id=record["clinic_id"],
            **clean,
        )
        try:
            with db.begin_nested():
                db.add(patient)
        except IntegrityError as exc:
            if not is_oib_conflict(exc):
                raise
            continue
        created += 1

    imp.rows = [_kept(r) for r in imp.rows]
    counts = {"created": created, "skipped": len(imp.rows) - created}
    imp.status = "committed"
    imp.committed_at = datetime.now(UTC)
    imp.counts = counts
    record_audit(
        db,
        organization_id=staff.organization_id,
        action=AuditAction.CREATE,
        entity_type="patient_import",
        entity_id=imp.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
        detail=counts,
    )
    return CommitOut(**counts).model_dump()
