from testing import fake_password

from pathlib import Path

import pytest
import redis
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import create_app
from app.identity.core.passwords import hash_password
from app.identity.core.totp import encrypt_secret
from app.identity.models import Account, Clinic, Organization, Role, StaffClinic, StaffMember
from app.people.models import Patient
from app.platform.config import TestConfig
from app.platform.db import make_engine
from app.platform.events import clear_subscribers

BACKEND_DIR = Path(__file__).resolve().parent


@pytest.fixture
def _clean_redis():
    client = redis.Redis.from_url(TestConfig.REDIS_URL)
    client.flushdb()
    yield
    client.close()


@pytest.fixture(autouse=True)
def _clean_subscribers():
    clear_subscribers()
    yield
    clear_subscribers()


@pytest.fixture
def app(_clean_redis):
    app = create_app(TestConfig)
    yield app
    app.extensions["db_engine"].dispose()
    app.config["SESSION_REDIS"].close()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def _owner_engine():
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TestConfig.DATABASE_OWNER_URL)
    command.upgrade(cfg, "head")
    engine = make_engine(TestConfig.DATABASE_OWNER_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def owner_engine(_owner_engine):
    yield _owner_engine
    with _owner_engine.begin() as conn:
        tables = (
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )
        if tables:
            names = ", ".join(f'"{t}"' for t in tables)
            conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def app_session(owner_engine):
    engine = make_engine(TestConfig.DATABASE_URL)
    session = Session(engine, expire_on_commit=False)
    yield session
    session.rollback()
    session.close()
    engine.dispose()


@pytest.fixture
def make_org(owner_engine):
    def _make(name: str) -> Organization:
        with Session(owner_engine, expire_on_commit=False) as s:
            org = Organization(name=name)
            s.add(org)
            s.commit()
            return org

    return _make


@pytest.fixture
def make_clinic(owner_engine):
    def _make(org: Organization, name: str) -> Clinic:
        with Session(owner_engine, expire_on_commit=False) as s:
            clinic = Clinic(organization_id=org.id, name=name)
            s.add(clinic)
            s.commit()
            return clinic

    return _make


@pytest.fixture
def make_patient(owner_engine):
    def _make(org: Organization, first_name: str = "Testa", last_name: str = "Testić", **fields) -> Patient:
        with Session(owner_engine, expire_on_commit=False) as s:
            patient = Patient(organization_id=org.id, first_name=first_name, last_name=last_name, **fields)
            s.add(patient)
            s.commit()
            s.refresh(patient)
            return patient

    return _make


@pytest.fixture
def make_account(owner_engine):
    def _make(email: str, password: str = fake_password('account'), totp_secret: str | None = None) -> Account:
        with Session(owner_engine, expire_on_commit=False) as s:
            account = Account(
                email=email,
                password_hash=hash_password(password),
                totp_secret_encrypted=(
                    encrypt_secret(totp_secret, TestConfig.TOTP_ENCRYPTION_KEY) if totp_secret is not None else None
                ),
                totp_enabled=totp_secret is not None,
            )
            s.add(account)
            s.commit()
            return account

    return _make


@pytest.fixture
def make_staff(owner_engine, make_account):
    def _make(
        org: Organization,
        account_or_email: Account | str,
        roles=(Role.RECEPTIONIST,),
        clinics=(),
        full_name: str = "Test Staff",
        is_active: bool = True,
    ) -> StaffMember:
        account = (
            make_account(account_or_email) if isinstance(account_or_email, str) else account_or_email
        )
        with Session(owner_engine, expire_on_commit=False) as s:
            staff = StaffMember(
                organization_id=org.id,
                account_id=account.id,
                full_name=full_name,
                roles=list(roles),
                is_active=is_active,
            )
            s.add(staff)
            s.flush()
            for clinic in clinics:
                s.add(StaffClinic(organization_id=org.id, staff_member_id=staff.id, clinic_id=clinic.id))
            s.commit()
            return staff

    return _make


@pytest.fixture
def csrf():
    def _csrf(client) -> dict:
        r = client.get("/api/auth/csrf")
        assert r.status_code == 200, r.get_json()
        return {"X-CSRF-Token": r.get_json()["csrf_token"]}

    return _csrf


@pytest.fixture
def login(csrf):
    def _login(
        client, email: str, password: str = fake_password('account'), organization_id=None, totp_secret: str | None = None
    ) -> dict:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        body = r.get_json()
        assert r.status_code == 200, body
        if body["status"] == "totp_required":
            assert totp_secret is not None, "account has TOTP: pass totp_secret"
            import pyotp

            r = client.post("/api/auth/totp", json={"code": pyotp.TOTP(totp_secret).now()})
            body = r.get_json()
            assert r.status_code == 200, body
        if body["status"] == "choose_organization":
            assert organization_id is not None, "several Organizations: pass organization_id"
            r = client.post(
                "/api/auth/organization",
                json={"organization_id": str(organization_id)},
                headers=csrf(client),
            )
            assert r.status_code == 200, r.get_json()
        else:
            assert body == {"status": "ok"}, body
        me = client.get("/api/auth/me")
        assert me.status_code == 200, me.get_json()
        return me.get_json()

    return _login
