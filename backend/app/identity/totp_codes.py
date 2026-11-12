from uuid import UUID

from flask import current_app
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.identity.core.totp import decrypt_secret, matched_step
from app.identity.models import Account


def accept_totp_code(db: Session, account: Account, code: str) -> bool:
    if not account.totp_secret_encrypted:
        return False
    secret = decrypt_secret(account.totp_secret_encrypted, current_app.config["TOTP_ENCRYPTION_KEY"])
    step = matched_step(secret, code)
    if step is None:
        return False
    return _claim_step(db, account.id, step)


def _claim_step(db: Session, account_id: UUID, step: int) -> bool:
    result = db.execute(
        update(Account)
        .where(
            Account.id == account_id,
            or_(Account.totp_last_step.is_(None), Account.totp_last_step < step),
        )
        .values(totp_last_step=step)
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount == 1
