from testing import fake_email, fake_password

import pyotp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.identity import Role
from app.identity import session as session_module

PASSWORD = fake_password('account')


def _login(client, email):
    return client.post("/api/auth/login", json={"email": email, "password": PASSWORD})


def _totp(client, code):
    return client.post("/api/auth/totp", json={"code": code})


def _mfa_account(make_account, email=fake_email('mgr', 'clinic.example.test')):
    secret = pyotp.random_base32()
    return secret, make_account(email, totp_secret=secret)


def test_totp_account_needs_code(client, make_org, make_staff, make_account):
    secret, acc = _mfa_account(make_account)
    make_staff(make_org("Smile"), acc, roles=(Role.CLINIC_MANAGER,))
    assert _login(client, fake_email('mgr', 'clinic.example.test')).get_json() == {"status": "totp_required"}
    assert client.get("/api/auth/me").status_code == 401
    r = _totp(client, pyotp.TOTP(secret).now())
    assert (r.status_code, r.get_json()) == (200, {"status": "ok"})
    assert client.get("/api/auth/me").status_code == 200


def test_totp_without_pending_login_is_unauthenticated(client):
    r = _totp(client, "123456")
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})


def test_wrong_totp_code_rejected_and_audited(client, owner_engine, capsys, make_org, make_staff, make_account):
    secret, acc = _mfa_account(make_account)
    org_a, org_b = make_org("A"), make_org("B")
    make_staff(org_a, acc, roles=(Role.CLINIC_MANAGER,))
    make_staff(org_b, acc, roles=(Role.RECEPTIONIST,))
    _login(client, fake_email('mgr', 'clinic.example.test'))
    good = pyotp.TOTP(secret).now()
    wrong = "000000" if good != "000000" else "111111"
    r = _totp(client, wrong)
    assert (r.status_code, r.get_json()) == (401, {"error": "invalid_code"})
    assert client.get("/api/auth/me").status_code == 401
    with Session(owner_engine) as s:
        rows = s.execute(
            text("SELECT action, organization_id, detail FROM audit_entries WHERE action = 'login_failed'")
        ).all()
    assert {r.organization_id for r in rows} == {org_a.id, org_b.id}
    assert all(r.detail == {"factor": "totp"} for r in rows)
    out = capsys.readouterr()
    logged = out.out + out.err
    assert wrong not in logged and secret not in logged


def test_totp_success_continues_with_organization_choice(client, make_org, make_staff, make_account, csrf):
    secret, acc = _mfa_account(make_account)
    org_a, org_b = make_org("A"), make_org("B")
    make_staff(org_a, acc, roles=(Role.RECEPTIONIST,))
    make_staff(org_b, acc, roles=(Role.RECEPTIONIST,))
    _login(client, fake_email('mgr', 'clinic.example.test'))
    r = _totp(client, pyotp.TOTP(secret).now())
    body = r.get_json()
    assert r.status_code == 200 and body["status"] == "choose_organization"
    assert {o["id"] for o in body["organizations"]} == {str(org_a.id), str(org_b.id)}
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/organization", json={"organization_id": str(org_a.id)}, headers=csrf(client))
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_totp_success_keeps_the_original_sign_in_time(client, monkeypatch, make_org, make_staff, make_account):
    secret, acc = _mfa_account(make_account)
    make_staff(make_org("Smile"), acc)
    clock = [1_000_000.0]
    monkeypatch.setattr(session_module, "now", lambda: clock[0])
    _login(client, fake_email('mgr', 'clinic.example.test'))
    clock[0] += 60
    assert _totp(client, pyotp.TOTP(secret).now()).status_code == 200
    with client.session_transaction() as s:
        assert s["authenticated_at"] == 1_000_000
    clock[0] = 1_000_000 + 12 * 3600 + 1
    assert client.get("/api/auth/me").status_code == 401


def test_totp_code_cannot_be_replayed(client, csrf, make_org, make_staff, make_account):
    secret, acc = _mfa_account(make_account)
    make_staff(make_org("Smile"), acc)
    code = pyotp.TOTP(secret).now()
    _login(client, fake_email('mgr', 'clinic.example.test'))
    assert _totp(client, code).status_code == 200
    assert client.post("/api/auth/logout", json={}, headers=csrf(client)).status_code == 204
    _login(client, fake_email('mgr', 'clinic.example.test'))
    r = _totp(client, code)
    assert (r.status_code, r.get_json()) == (401, {"error": "invalid_code"})
    assert client.get("/api/auth/me").status_code == 401


def test_pending_totp_stage_expires_after_ten_minutes(client, monkeypatch, make_org, make_staff, make_account):
    secret, acc = _mfa_account(make_account)
    make_staff(make_org("Smile"), acc)
    clock = [1_000_000.0]
    monkeypatch.setattr(session_module, "now", lambda: clock[0])
    _login(client, fake_email('mgr', 'clinic.example.test'))
    clock[0] += 10 * 60 + 1
    r = _totp(client, pyotp.TOTP(secret).now())
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})
    with client.session_transaction() as s:
        assert "pending_account_id" not in s


def test_pending_totp_session_cannot_use_account_endpoints(client, make_org, make_staff, make_account):
    _, acc = _mfa_account(make_account)
    org = make_org("Smile")
    make_staff(org, acc, roles=(Role.CLINIC_MANAGER,))
    assert _login(client, fake_email('mgr', 'clinic.example.test')).get_json() == {"status": "totp_required"}
    unauthenticated = (401, {"error": "unauthenticated"})
    r = client.get("/api/auth/organizations")
    assert (r.status_code, r.get_json()) == unauthenticated
    r = client.post("/api/auth/organization", json={"organization_id": str(org.id)})
    assert (r.status_code, r.get_json()) == unauthenticated
    r = client.post("/api/auth/totp/enroll", json={})
    assert (r.status_code, r.get_json()) == unauthenticated
    r = client.post("/api/auth/totp/confirm", json={"code": "123456"})
    assert (r.status_code, r.get_json()) == unauthenticated
