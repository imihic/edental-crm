from testing import fake_email, fake_password

import pyotp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.identity import Role

PASSWORD = fake_password('account')


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _audit(owner_engine):
    with Session(owner_engine) as s:
        return s.execute(text("SELECT action, organization_id, staff_member_id, account_id FROM audit_entries ORDER BY occurred_at")).all()


def test_single_org_login_then_me(client, make_org, make_clinic, make_staff):
    org = make_org("Smile")
    c = make_clinic(org, "Centar")
    make_staff(org, fake_email('testa', 'clinic.example.test'), roles=(Role.RECEPTIONIST,), clinics=[c], full_name="Testa")
    r = _login(client, f" {fake_email('Testa', 'Clinic.example.test')} ")
    assert (r.status_code, r.get_json()) == (200, {"status": "ok"})
    me = client.get("/api/auth/me").get_json()
    assert me["account"]["email"] == fake_email('testa', 'clinic.example.test') and me["staff"]["roles"] == ["receptionist"]
    assert me["clinics"] == [{"id": str(c.id), "name": "Centar"}] and me["organizations_count"] == 1


def test_unknown_email_and_wrong_password_indistinguishable(client, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'))
    unknown = _login(client, fake_email('nobody', 'clinic.example.test'))
    wrong = _login(client, fake_email('testa', 'clinic.example.test'), "wrong password")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_json() == wrong.get_json() == {"error": "invalid_credentials"}
    assert client.get("/api/auth/me").status_code == 401


def test_account_without_active_membership_cannot_sign_in(
    client, owner_engine, make_org, make_account, make_staff
):
    make_account(fake_email('loner', 'clinic.example.test'))
    make_staff(make_org("Smile"), fake_email('gone', 'clinic.example.test'), is_active=False)
    for email in (fake_email('loner', 'clinic.example.test'), fake_email('gone', 'clinic.example.test')):
        r = _login(client, email)
        assert (r.status_code, r.get_json()) == (401, {"error": "invalid_credentials"})
    assert client.get("/api/auth/me").status_code == 401
    assert _audit(owner_engine) == []


def test_totp_enabled_account_gets_totp_required(client, make_org, make_account, make_staff):
    acc = make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=pyotp.random_base32())
    make_staff(make_org("Smile"), acc, roles=(Role.CLINIC_MANAGER,))
    r = _login(client, fake_email('mgr', 'clinic.example.test'))
    assert (r.status_code, r.get_json()) == (200, {"status": "totp_required"})
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/organizations").status_code == 401


def test_session_id_rotates_on_login(client, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'))
    client.get("/api/auth/csrf")
    before = client.get_cookie("crm_session").value
    assert _login(client, fake_email('testa', 'clinic.example.test')).status_code == 200
    cookie = client.get_cookie("crm_session")
    assert cookie.value != before
    assert cookie.http_only and cookie.same_site == "Lax"
    assert client.get("/api/auth/me").status_code == 200
    client.set_cookie("crm_session", before)
    assert client.get("/api/auth/me").status_code == 401


def test_validation_error_names_fields_without_echoing_input(client):
    r = client.post("/api/auth/login", json={"email": fake_email('secret-testa', 'clinic.example.test')})
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["password"]})
    assert b"secret-testa" not in r.data


def test_non_json_mutation_rejected(client):
    r = client.post("/api/auth/login", data={"email": fake_email('a', 'b.example.test'), "password": "x"})
    assert (r.status_code, r.get_json()) == (415, {"error": "json_required"})


def test_audit_trail_for_failed_and_successful_login(client, owner_engine, make_org, make_staff):
    org = make_org("Smile")
    staff = make_staff(org, fake_email('testa', 'clinic.example.test'))
    assert _login(client, fake_email('testa', 'clinic.example.test'), "wrong").status_code == 401
    assert _login(client, fake_email('testa', 'clinic.example.test')).status_code == 200
    entries = _audit(owner_engine)
    assert [e.action for e in entries] == ["login_failed", "login"]
    for e in entries:
        assert (e.organization_id, e.staff_member_id, e.account_id) == (org.id, staff.id, staff.account_id)


def test_failed_login_audited_in_every_member_org(
    client, owner_engine, make_org, make_account, make_staff
):
    acc = make_account(fake_email('dr', 'x.example.test'))
    a, b, c = make_org("Alpha"), make_org("Beta"), make_org("Gamma")
    sa = make_staff(a, acc, roles=(Role.DENTIST,))
    sb = make_staff(b, acc, roles=(Role.DENTIST,))
    make_staff(c, acc, roles=(Role.DENTIST,), is_active=False)
    r = _login(client, fake_email('dr', 'x.example.test'), "wrong")
    assert (r.status_code, r.get_json()) == (401, {"error": "invalid_credentials"})
    entries = _audit(owner_engine)
    assert {(e.action, e.organization_id, e.staff_member_id, e.account_id) for e in entries} == {
        ("login_failed", a.id, sa.id, acc.id),
        ("login_failed", b.id, sb.id, acc.id),
    }
    _login(client, fake_email('nobody', 'x.example.test'))
    with Session(owner_engine) as s:
        assert s.execute(text("SELECT count(*) FROM audit_entries")).scalar_one() == 2
