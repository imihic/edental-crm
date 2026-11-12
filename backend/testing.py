from functools import cache
import secrets

_EMAIL_RUN = secrets.token_hex(4)


def fake_email(label: str, domain: str = "example.test") -> str:
    return f"{label}-{_EMAIL_RUN}@{domain}"


@cache
def fake_password(label: str = "account") -> str:
    return secrets.token_urlsafe(24)
