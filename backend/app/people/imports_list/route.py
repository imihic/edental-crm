from flask_openapi3 import APIBlueprint, Tag
from sqlalchemy import select

from app.identity import Role, login_required, require_role
from app.people.import_service import ImportItem, ImportListOut, blank_expired, is_expired
from app.people.models import PatientImport
from app.platform.db import get_session
from app.platform.errors import VALIDATION_ERROR_RESPONSES, ErrorResponse

api = APIBlueprint(
    "imports_list", __name__, abp_tags=[Tag(name="imports")], abp_responses=VALIDATION_ERROR_RESPONSES
)

LIST_LIMIT = 100


@api.get("/api/imports", responses={200: ImportListOut, 401: ErrorResponse, 403: ErrorResponse})
@login_required
@require_role(Role.CLINIC_MANAGER)
def list_imports():
    """The Organization's most recent Imports (newest first); rows are never listed."""
    db = get_session()
    blank_expired(db)
    imports = db.scalars(
        select(PatientImport).order_by(PatientImport.created_at.desc(), PatientImport.id).limit(LIST_LIMIT)
    )
    items = [
        ImportItem(
            id=i.id,
            filename=i.filename,
            status="expired" if is_expired(i) else i.status,
            counts=i.counts,
            created_at=i.created_at,
            committed_at=i.committed_at,
        )
        for i in imports
    ]
    return ImportListOut(items=items).model_dump(mode="json")
