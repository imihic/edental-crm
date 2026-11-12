from testing import fake_email

from sqlalchemy import text
from sqlalchemy.orm import Session


def test_mutation_without_csrf_rejected(client, login, csrf, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'))
    login(client, fake_email('testa', 'clinic.example.test'))
    r = client.post("/api/auth/logout", json={})
    assert (r.status_code, r.get_json()) == (403, {"error": "csrf_failed"})
    r = client.post("/api/auth/logout", json={}, headers={"X-CSRF-Token": "forged"})
    assert (r.status_code, r.get_json()) == (403, {"error": "csrf_failed"})
    assert client.get("/api/auth/me").status_code == 200
    r = client.post("/api/auth/logout", json={}, headers=csrf(client))
    assert r.status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_logout_is_audited(client, login, csrf, owner_engine, make_org, make_staff):
    org = make_org("Smile")
    staff = make_staff(org, fake_email('testa', 'clinic.example.test'))
    login(client, fake_email('testa', 'clinic.example.test'))
    assert client.post("/api/auth/logout", json={}, headers=csrf(client)).status_code == 204
    with Session(owner_engine) as s:
        e = s.execute(
            text(
                "SELECT organization_id, staff_member_id, account_id FROM audit_entries "
                "WHERE action = 'logout'"
            )
        ).one()
    assert (e.organization_id, e.staff_member_id, e.account_id) == (org.id, staff.id, staff.account_id)


def test_logout_without_session_is_harmless(client):
    assert client.post("/api/auth/logout", json={}).status_code == 204
