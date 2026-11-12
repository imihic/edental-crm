import os
import secrets

from cryptography.fernet import Fernet


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://crm_app@localhost:5433/crm")
    DATABASE_OWNER_URL = os.environ.get(
        "DATABASE_OWNER_URL", "postgresql://crm_owner@localhost:5433/crm"
    )
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380/0")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)
    TOTP_ENCRYPTION_KEY = os.environ.get("TOTP_ENCRYPTION_KEY")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024


class TestConfig(Config):
    __test__ = False
    DATABASE_URL = os.environ.get(
        "CRM_TEST_DATABASE_URL", "postgresql://crm_app@localhost:5433/crm_test"
    )
    DATABASE_OWNER_URL = os.environ.get(
        "CRM_TEST_DATABASE_OWNER_URL", "postgresql://crm_owner@localhost:5433/crm_test"
    )
    REDIS_URL = os.environ.get("CRM_TEST_REDIS_URL", "redis://localhost:6380/15")
    SESSION_COOKIE_SECURE = False
    TESTING = True
    SECRET_KEY = secrets.token_hex(32)
    TOTP_ENCRYPTION_KEY = Fernet.generate_key().decode()
