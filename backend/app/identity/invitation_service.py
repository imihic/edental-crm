import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

TOKEN_FORMAT = re.compile(r"^[A-Za-z0-9_-]{43}$")
INVITATION_TTL = timedelta(hours=72)


def now() -> datetime:
    return datetime.now(UTC)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
