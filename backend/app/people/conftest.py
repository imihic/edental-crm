from testing import fake_email

import pytest


@pytest.fixture
def signed_in(client, login, csrf, make_org, make_staff):
    org = make_org("Smile")
    staff = make_staff(org, fake_email('testa', 'clinic.example.test'))
    login(client, fake_email('testa', 'clinic.example.test'))
    return org, staff, csrf(client)


@pytest.fixture
def audit_rows(owner_engine):
    from sqlalchemy import text

    def _rows(action: str | None = None, entity_type: str = "patient"):
        sql = "SELECT action, entity_type, entity_id, staff_member_id, detail FROM audit_entries WHERE entity_type = :e"
        params = {"e": entity_type}
        if action:
            sql += " AND action = :a"
            params["a"] = action
        with owner_engine.connect() as conn:
            return conn.execute(text(sql + " ORDER BY occurred_at"), params).all()

    return _rows


@pytest.fixture
def manager_in(client, login, csrf, make_org, make_account, make_staff, make_clinic):
    import pyotp

    from app.identity import Role

    secret = pyotp.random_base32()
    org = make_org("Smile")
    make_clinic(org, "Centar")
    make_clinic(org, "Zapad")
    staff = make_staff(org, make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=secret), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'), totp_secret=secret)
    return org, staff, csrf(client)


@pytest.fixture
def upload(client):
    import base64

    def _upload(headers, content, filename: str = "patients.csv"):
        raw = content.encode("utf-8") if isinstance(content, str) else content
        return client.post(
            "/api/imports/patients/preview",
            json={"filename": filename, "content_base64": base64.b64encode(raw).decode()},
            headers=headers,
        )

    return _upload


@pytest.fixture
def make_lead(owner_engine):
    from sqlalchemy.orm import Session

    from app.people.models import Lead

    def _make(org, clinic, full_name: str = "Testan Testač", **fields) -> Lead:
        with Session(owner_engine, expire_on_commit=False) as s:
            lead = Lead(organization_id=org.id, clinic_id=clinic.id, full_name=full_name, **fields)
            s.add(lead)
            s.commit()
            s.refresh(lead)
            return lead

    return _make
