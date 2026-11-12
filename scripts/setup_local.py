import os
from pathlib import Path
import secrets

from cryptography.fernet import Fernet
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[1]


def database_url(username: str, password: str, database: str) -> str:
    return URL.create(
        "postgresql+psycopg",
        username=username,
        password=password,
        host="localhost",
        port=5433,
        database=database,
    ).render_as_string(hide_password=False)


def main() -> None:
    paths = [ROOT / ".env", ROOT / "backend" / ".env"]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise SystemExit("Local configuration already exists. Keep it when using an existing database.")

    owner_password = secrets.token_urlsafe(24)
    app_password = secrets.token_urlsafe(24)
    database_values = {
        "DATABASE_URL": database_url("crm_app", app_password, "crm"),
        "DATABASE_OWNER_URL": database_url("crm_owner", owner_password, "crm"),
        "CRM_TEST_DATABASE_URL": database_url("crm_app", app_password, "crm_test"),
        "CRM_TEST_DATABASE_OWNER_URL": database_url("crm_owner", owner_password, "crm_test"),
        "REDIS_URL": "redis://localhost:6380/0",
        "SECRET_KEY": secrets.token_hex(32),
        "TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "SESSION_COOKIE_SECURE": "false",
    }
    compose_values = {
        "CRM_OWNER_PASSWORD": owner_password,
        "CRM_APP_PASSWORD": app_password,
    }
    created = []
    try:
        for path, values in zip(paths, [compose_values, database_values]):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
                target.write("".join(f"{name}={value}\n" for name, value in values.items()))
    except OSError:
        for path in created:
            path.unlink()
        raise
    print("Created local configuration in .env and backend/.env.")


if __name__ == "__main__":
    main()
