import hmac
import time

import pyotp
from cryptography.fernet import Fernet

ISSUER = "Dental CRM"
STEP_OFFSETS = (-1, 0, 1)


def new_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str, key: str) -> str:
    return Fernet(key.encode()).encrypt(secret.encode()).decode()


def decrypt_secret(token: str, key: str) -> str:
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def matched_step(secret: str, code: str, at: float | None = None) -> int | None:
    totp = pyotp.TOTP(secret)
    now = time.time() if at is None else at
    current = int(now) // totp.interval
    matched = None
    for offset in STEP_OFFSETS:
        step = current + offset
        if hmac.compare_digest(totp.generate_otp(step).encode(), code.encode()) and matched is None:
            matched = step
    return matched


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)
