from testing import fake_email, fake_password

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.identity import Role


def _two_org_account(make_org, make_clinic, make_staff, make_account):
    acc = make_account(fake_email('dr', 'x.example.test'))
    a, b = make_org("Alpha"), make_org("Beta")
    a1, b1 = make_clinic(a, "A-1"), make_clinic(b, "B-1")
    make_staff(a, acc, roles=(Role.DENTIST,), clinics=[a1])
    make_staff(b, acc, roles=(Role.DENTIST,), clinics=[b1])
    return acc, a, b


def test_two_orgs_requires_choice_and_isolates(client, csrf, make_org, make_clinic, make_staff, make_account):
    _, a, b = _two_org_account(make_org, make_clinic, make_staff, make_account)
    r = client.post("/api/auth/login", json={"email": fake_email('dr', 'x.example.test'), "password": fake_password('account')}).get_json()
    assert r["status"] == "choose_organization" and [o["name"] for o in r["organizations"]] == ["Alpha", "Beta"]
    assert {o["id"] for o in r["organizations"]} == {str(a.id), str(b.id)}
    assert client.get("/api/auth/me").status_code == 401
    r = client.post("/api/auth/organization", json={"organization_id": str(a.id)}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (200, {"status": "ok"})
    me = client.get("/api/auth/me").get_json()
    assert [c["name"] for c in me["clinics"]] == ["A-1"]
    assert me["organization"]["name"] == "Alpha" and me["organizations_count"] == 2


def test_list_organizations_needs_authenticated_account(client, make_org, make_clinic, make_staff, make_account):
    assert client.get("/api/auth/organizations").status_code == 401
    _two_org_account(make_org, make_clinic, make_staff, make_account)
    client.post("/api/auth/login", json={"email": fake_email('dr', 'x.example.test'), "password": fake_password('account')})
    r = client.get("/api/auth/organizations")
    assert r.status_code == 200
    assert [o["name"] for o in r.get_json()["organizations"]] == ["Alpha", "Beta"]


def test_choosing_foreign_org_is_forbidden(client, csrf, make_org, make_clinic, make_staff, make_account):
    _two_org_account(make_org, make_clinic, make_staff, make_account)
    foreign = make_org("Foreign")
    make_staff(foreign, fake_email('someone', 'else.example.test'))
    client.post("/api/auth/login", json={"email": fake_email('dr', 'x.example.test'), "password": fake_password('account')})
    r = client.post("/api/auth/organization", json={"organization_id": str(foreign.id)}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (403, {"error": "forbidden"})
    assert client.get("/api/auth/me").status_code == 401


def test_choosing_without_password_step_is_unauthenticated(client, csrf, make_org):
    org = make_org("Alpha")
    r = client.post("/api/auth/organization", json={"organization_id": str(org.id)}, headers=csrf(client))
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})


def test_switch_organization_rebinds_and_audits(
    client, csrf, login, owner_engine, make_org, make_clinic, make_staff, make_account
):
    _, a, b = _two_org_account(make_org, make_clinic, make_staff, make_account)
    login(client, fake_email('dr', 'x.example.test'), organization_id=a.id)
    before = client.get_cookie("crm_session").value
    r = client.post("/api/auth/organization", json={"organization_id": str(b.id)}, headers=csrf(client))
    assert r.status_code == 200
    assert client.get_cookie("crm_session").value != before
    me = client.get("/api/auth/me").get_json()
    assert me["organization"]["name"] == "Beta" and [c["name"] for c in me["clinics"]] == ["B-1"]
    with Session(owner_engine) as s:
        logins = s.scalars(text("SELECT organization_id FROM audit_entries WHERE action = 'login'")).all()
    assert sorted(map(str, logins)) == sorted([str(a.id), str(b.id)])
