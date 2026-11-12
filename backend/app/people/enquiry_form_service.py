import re
import secrets
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

KEY_FORMAT = re.compile(r"^[A-Za-z0-9_-]{20,64}$")


def new_key() -> str:
    return secrets.token_urlsafe(24)


def clinic_exists(session: Session, clinic_id: UUID) -> bool:
    return session.execute(text("SELECT 1 FROM clinics WHERE id = :id"), {"id": clinic_id}).first() is not None


def ensure_form(session: Session, *, organization_id: UUID, clinic_id: UUID) -> tuple[UUID, str, bool]:
    session.execute(
        text(
            "INSERT INTO enquiry_forms (id, organization_id, clinic_id, key) "
            "VALUES (:id, :org, :clinic, :key) ON CONFLICT (clinic_id) DO NOTHING"
        ),
        {"id": uuid4(), "org": organization_id, "clinic": clinic_id, "key": new_key()},
    )
    row = session.execute(
        text("SELECT id, key, enabled FROM enquiry_forms WHERE clinic_id = :clinic"), {"clinic": clinic_id}
    ).one()
    return row.id, row.key, row.enabled
