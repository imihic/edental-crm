from testing import fake_email, fake_password

from datetime import UTC, datetime

import pyotp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.identity import Role


def _account_row(owner_engine, email):
    with Session(owner_engine) as s:
        return s.execute(
            text("SELECT totp_enabled, totp_secret_encrypted FROM accounts WHERE email = :e"), {"e": email}
        ).one()


def _enroll(client, csrf):
    r = client.post("/api/auth/totp/enroll", json={}, headers=csrf(client))
    assert r.status_code == 200, r.get_json()
    uri = r.get_json()["otpauth_uri"]
    return uri, pyotp.parse_uri(uri).secret


def test_manager_without_totp_is_fenced(client, login, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    me = login(client, fake_email('mgr', 'clinic.example.test'))
    assert me["totp_enrollment_required"] is True
    r = client.get("/api/_test/protected")
    assert (r.status_code, r.get_json()) == (403, {"error": "totp_enrollment_required"})
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/organizations").status_code == 200
    assert client.get("/api/auth/csrf").status_code == 200


def test_dentist_who_is_also_manager_is_fenced(client, login, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('dr', 'clinic.example.test'), roles=(Role.DENTIST, Role.CLINIC_MANAGER))
    login(client, fake_email('dr', 'clinic.example.test'))
    assert client.get("/api/_test/protected").status_code == 403


def test_manager_enrolls_and_is_unfenced(client, login, csrf, owner_engine, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    uri, secret = _enroll(client, csrf)
    assert uri.startswith("otpauth://totp/Dental%20CRM:")
    enabled, stored = _account_row(owner_engine, fake_email('mgr', 'clinic.example.test'))
    assert enabled is False and stored and secret not in stored
    assert client.get("/api/_test/protected").status_code == 403
    r = client.post("/api/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (200, {"status": "ok"})
    assert _account_row(owner_engine, fake_email('mgr', 'clinic.example.test')).totp_enabled is True
    assert client.get("/api/_test/protected").get_json() == {"ok": True}
    assert client.get("/api/auth/me").get_json()["totp_enrollment_required"] is False


def test_wrong_confirm_code_keeps_account_fenced(client, login, csrf, owner_engine, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    _, secret = _enroll(client, csrf)
    good = pyotp.TOTP(secret).now()
    wrong = "000000" if good != "000000" else "111111"
    r = client.post("/api/auth/totp/confirm", json={"code": wrong}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (400, {"error": "invalid_code"})
    assert _account_row(owner_engine, fake_email('mgr', 'clinic.example.test')).totp_enabled is False
    assert client.get("/api/_test/protected").status_code == 403


def test_confirm_without_pending_secret_is_invalid_code(client, login, csrf, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    r = client.post("/api/auth/totp/confirm", json={"code": "123456"}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (400, {"error": "invalid_code"})


def test_enroll_when_already_enabled_is_conflict(client, csrf, owner_engine, make_org, make_staff, make_account):
    secret = pyotp.random_base32()
    acc = make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=secret)
    make_staff(make_org("Smile"), acc, roles=(Role.CLINIC_MANAGER,))
    client.post("/api/auth/login", json={"email": fake_email('mgr', 'clinic.example.test'), "password": fake_password('account')})
    assert client.post("/api/auth/totp", json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    before = _account_row(owner_engine, fake_email('mgr', 'clinic.example.test'))
    r = client.post("/api/auth/totp/enroll", json={}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (409, {"error": "totp_already_enabled"})
    assert _account_row(owner_engine, fake_email('mgr', 'clinic.example.test')) == before


def test_enroll_requires_sign_in(client):
    r = client.post("/api/auth/totp/enroll", json={})
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})
    r = client.post("/api/auth/totp/confirm", json={"code": "123456"})
    assert r.status_code == 401


def test_receptionist_without_totp_not_fenced(client, login, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'), roles=(Role.RECEPTIONIST,))
    me = login(client, fake_email('testa', 'clinic.example.test'))
    assert me["totp_enrollment_required"] is False
    assert client.get("/api/_test/protected").get_json() == {"ok": True}


def test_fence_follows_bound_org(client, login, csrf, make_org, make_staff, make_account):
    acc = make_account(fake_email('multi', 'clinic.example.test'))
    org_a, org_b = make_org("A"), make_org("B")
    make_staff(org_a, acc, roles=(Role.CLINIC_MANAGER,))
    make_staff(org_b, acc, roles=(Role.RECEPTIONIST,))
    login(client, fake_email('multi', 'clinic.example.test'), organization_id=org_b.id)
    assert client.get("/api/_test/protected").status_code == 200
    r = client.post("/api/auth/organization", json={"organization_id": str(org_a.id)}, headers=csrf(client))
    assert r.status_code == 200
    assert client.get("/api/_test/protected").status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_confirm_code_cannot_be_replayed_at_sign_in(client, login, csrf, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    _, secret = _enroll(client, csrf)
    code = pyotp.TOTP(secret).now()
    r = client.post("/api/auth/totp/confirm", json={"code": code}, headers=csrf(client))
    assert r.status_code == 200
    assert client.post("/api/auth/logout", json={}, headers=csrf(client)).status_code == 204
    r = client.post("/api/auth/login", json={"email": fake_email('mgr', 'clinic.example.test'), "password": fake_password('account')})
    assert r.get_json() == {"status": "totp_required"}
    r = client.post("/api/auth/totp", json={"code": code})
    assert (r.status_code, r.get_json()) == (401, {"error": "invalid_code"})


def test_confirm_rejects_a_step_already_used(client, login, csrf, owner_engine, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    _, secret = _enroll(client, csrf)
    totp = pyotp.TOTP(secret)
    code = totp.now()
    with Session(owner_engine) as s, s.begin():
        s.execute(
            text(f"""UPDATE accounts SET totp_last_step = :s WHERE email = {fake_email("'mgr", 'clinic.example.test')}'"""),
            {"s": totp.timecode(datetime.now(UTC)) + 1},
        )
    r = client.post("/api/auth/totp/confirm", json={"code": code}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (400, {"error": "invalid_code"})
    assert _account_row(owner_engine, fake_email('mgr', 'clinic.example.test')).totp_enabled is False


def test_fenced_manager_can_log_out(client, login, csrf, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    r = client.post("/api/auth/logout", json={}, headers=csrf(client))
    assert r.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_enroll_again_returns_the_unconfirmed_secret(client, login, csrf, owner_engine, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    first_uri, secret = _enroll(client, csrf)
    stored = _account_row(owner_engine, fake_email('mgr', 'clinic.example.test')).totp_secret_encrypted
    second_uri, _ = _enroll(client, csrf)
    assert second_uri == first_uri
    assert _account_row(owner_engine, fake_email('mgr', 'clinic.example.test')).totp_secret_encrypted == stored
    r = client.post("/api/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=csrf(client))
    assert r.status_code == 200


def test_confirm_is_audited_in_every_member_org(
    client, login, csrf, owner_engine, make_org, make_account, make_staff
):
    acc = make_account(fake_email('mgr', 'clinic.example.test'))
    a, b, gone = make_org("Alpha"), make_org("Beta"), make_org("Gone")
    sa = make_staff(a, acc, roles=(Role.CLINIC_MANAGER,))
    sb = make_staff(b, acc, roles=(Role.DENTIST,))
    make_staff(gone, acc, roles=(Role.DENTIST,), is_active=False)
    login(client, fake_email('mgr', 'clinic.example.test'), organization_id=a.id)
    _, secret = _enroll(client, csrf)
    r = client.post("/api/auth/totp/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=csrf(client))
    assert r.status_code == 200
    with Session(owner_engine) as s:
        rows = s.execute(
            text(
                "SELECT organization_id, staff_member_id, account_id, entity_type, entity_id, detail "
                "FROM audit_entries WHERE action = 'update'"
            )
        ).all()
    assert {(r.organization_id, r.staff_member_id) for r in rows} == {(a.id, sa.id), (b.id, sb.id)}
    assert all(
        (r.account_id, r.entity_type, r.entity_id, r.detail) == (acc.id, "account", acc.id, {"fields": ["totp"]})
        for r in rows
    )
