import base64
import binascii

from flask_openapi3 import APIBlueprint, Tag

from app.identity import Role, current_staff, login_required, require_role
from app.people.core.csv_import import TooManyRows, parse_patients_csv
from app.people.import_service import (
    MAX_FILE_BYTES,
    MAX_ROWS,
    PreviewIn,
    PreviewOut,
    analyse,
    blank_expired,
    counts_of,
)
from app.people.models import PatientImport
from app.people.patient_service import validation_failed
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ApiError, ErrorResponse, error_response

api = APIBlueprint(
    "import_preview", __name__, abp_tags=[Tag(name="imports")], abp_responses=VALIDATION_ERROR_RESPONSES
)

_MAX_BASE64_CHARS = (MAX_FILE_BYTES + 2) // 3 * 4


@api.post(
    "/api/imports/patients/preview",
    responses={200: PreviewOut, 401: ErrorResponse, 403: ErrorResponse, 413: ErrorResponse},
)
@login_required
@require_role(Role.CLINIC_MANAGER)
def preview_import(body: PreviewIn):
    """Parse a Patient CSV and store the checked rows for a later commit; nothing is saved as a Patient yet.

    Not audited: no patient data is created. The rows (personal data) are kept only under the Organization's RLS.
    """
    if len(body.content_base64) > _MAX_BASE64_CHARS:
        raise ApiError(413, "file_too_large")
    try:
        raw = base64.b64decode(body.content_base64, validate=True)
    except (binascii.Error, ValueError):
        return validation_failed(["content_base64"])
    if len(raw) > MAX_FILE_BYTES:
        raise ApiError(413, "file_too_large")
    try:
        parsed = parse_patients_csv(raw, max_rows=MAX_ROWS)
    except TooManyRows:
        return error_response(422, "too_many_rows")
    if "unsupported_file" in parsed.errors:
        return error_response(422, "unsupported_file")
    if parsed.errors:
        return error_response(422, "invalid_file", reasons=parsed.errors)

    db = get_session()
    staff = current_staff()
    blank_expired(db)
    records = analyse(db, parsed)
    counts = counts_of(records)
    imp = PatientImport(
        organization_id=staff.organization_id,
        filename=body.filename.strip() or "patients.csv",
        rows=records,
        created_by_staff_member_id=staff.id,
        counts=counts,
    )
    db.add(imp)
    db.flush()
    return PreviewOut(
        import_id=imp.id,
        rows=[
            {
                "line": r["line"],
                "status": r["status"],
                "errors": r["errors"],
                "duplicates": r["duplicates"],
                "in_file_duplicate_of_line": r["in_file_duplicate_of_line"],
            }
            for r in records
        ],
        ignored_columns=parsed.ignored_columns,
        counts=counts,
    ).model_dump(mode="json")
