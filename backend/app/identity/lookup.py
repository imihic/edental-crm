from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class AccountCandidate:
    id: UUID
    password_hash: str
    totp_enabled: bool
    totp_secret_encrypted: str | None


@dataclass(frozen=True)
class Membership:
    staff_member_id: UUID
    organization_id: UUID
    organization_name: str


def find_account_for_login(session: Session, email: str) -> AccountCandidate | None:
    row = session.execute(
        text("SELECT * FROM auth_find_account(:email)"), {"email": email.strip()}
    ).first()
    if row is None:
        return None
    return AccountCandidate(row.id, row.password_hash, row.totp_enabled, row.totp_secret_encrypted)


def list_memberships(session: Session, account_id: UUID) -> list[Membership]:
    rows = session.execute(
        text("SELECT * FROM auth_list_memberships(:account_id)"), {"account_id": account_id}
    )
    return [Membership(r.staff_member_id, r.organization_id, r.organization_name) for r in rows]
