from uuid import UUID

from sqlalchemy.orm import Session

from app.compliance.models import AuditAction, AuditEntry


def record_audit(
    session: Session,
    *,
    organization_id: UUID,
    action: AuditAction,
    entity_type: str,
    entity_id: UUID | None = None,
    staff_member_id: UUID | None = None,
    account_id: UUID | None = None,
    detail: dict | None = None,
) -> None:
    session.add(
        AuditEntry(
            organization_id=organization_id,
            staff_member_id=staff_member_id,
            account_id=account_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail or {},
        )
    )
