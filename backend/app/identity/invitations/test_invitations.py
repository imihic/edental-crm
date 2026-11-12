from testing import fake_email, fake_password

import hashlib
from uuid import uuid4

import pyotp
import pytest
from sqlalchemy import text

PASSWORD = fake_password('invitation')


def invite(client, headers, staff, **over):
    body = {
        "email": fake_email('New.Person', 'clinic.example.test'),
        "full_name": "New Person",
        "roles": ["dentist"],
        "clinic_ids": [str(staff.clinics_by_name["Zapad"].id)],
        **over,
    }
    return client.post("/api/invitations", json=body, headers=headers)


def token_of(response) -> str:
    return response.get_json()["url"].removeprefix("/invite/")


def accept(anon, token, **body):
    return anon.post(f"/api/public/invitations/{token}/accept", json={"password": PASSWORD, **body})


@pytest.fixture
def anon(app):
    return app.test_client()


def test_invite_returns_token_once_and_stores_only_its_hash(manager_in, client, db_rows):
    _, staff, headers = manager_in
    r = invite(client, headers, staff)
    assert r.status_code == 201
    body = r.get_json()
    token = token_of(r)
    assert len(token) == 43 and set(body) == {"id", "url", "expires_at"}
    [row] = db_rows("SELECT token_hash, email, status, expires_at - created_at AS ttl FROM invitations")
    assert row.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert row.email == fake_email('new.person', 'clinic.example.test') and row.status == "pending"
    assert str(row.ttl) == "3 days, 0:00:00"
    dump = " ".join(str(c) for r_ in db_rows("SELECT * FROM invitations") for c in r_)
    assert token not in dump
    listed = client.get("/api/invitations").get_json()["items"]
    assert [i["id"] for i in listed] == [body["id"]] and token not in str(listed)
    [audit] = db_rows("SELECT action, detail FROM audit_entries WHERE entity_type = 'invitation'")
    assert audit.action == "create" and audit.detail == {"roles": ["dentist"], "clinic_count": 1}


def test_invite_new_person_and_accept_with_password(manager_in, client, anon, login, db_rows):
    _, staff, headers = manager_in
    token = token_of(invite(client, headers, staff, roles=["dentist", "receptionist"]))
    info = anon.get(f"/api/public/invitations/{token}")
    assert (info.status_code, info.get_json()) == (
        200,
        {
            "organization_name": "Smile",
            "email": fake_email('new.person', 'clinic.example.test'),
            "full_name": "New Person",
            "account_exists": False,
        },
    )
    r = accept(anon, token)
    assert (r.status_code, r.get_json()) == (200, {"status": "accepted"})
    assert anon.get("/api/auth/me").status_code == 401
    login(client.application.test_client(), fake_email('new.person', 'clinic.example.test'), password=PASSWORD)
    [sm] = db_rows("SELECT id, roles::text[] AS roles FROM staff_members WHERE full_name = 'New Person'")
    assert sorted(sm.roles) == ["dentist", "receptionist"]
    [sc] = db_rows("SELECT clinic_id FROM staff_clinics WHERE staff_member_id = :i", i=sm.id)
    assert sc.clinic_id == staff.clinics_by_name["Zapad"].id
    [inv] = db_rows("SELECT status, accepted_at, accepted_staff_member_id FROM invitations")
    assert inv.status == "accepted" and inv.accepted_at and inv.accepted_staff_member_id == sm.id
    [audit] = db_rows(
        "SELECT staff_member_id, account_id, detail FROM audit_entries "
        "WHERE entity_type = 'staff_member' AND action = 'create' AND entity_id = :i",
        i=sm.id,
    )
    assert audit.staff_member_id == sm.id and audit.account_id and audit.detail == {}


def test_new_account_needs_long_password(manager_in, client, anon, db_rows):
    _, staff, headers = manager_in
    token = token_of(invite(client, headers, staff))
    r = accept(anon, token, password="short")
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["password"]})
    assert db_rows("SELECT status FROM invitations")[0].status == "pending"
    assert db_rows(f"""SELECT 1 FROM accounts WHERE email = {fake_email("'new.person", 'clinic.example.test')}'""") == []


def test_existing_account_accepts_with_password_and_totp(
    manager_in, client, anon, login, make_org, make_staff, make_account, db_rows, owner_engine
):
    _, staff, headers = manager_in
    secret = pyotp.random_base32()
    make_staff(make_org("Other"), make_account(fake_email('new.person', 'clinic.example.test'), password=PASSWORD, totp_secret=secret))
    token = token_of(invite(client, headers, staff))
    assert anon.get(f"/api/public/invitations/{token}").get_json()["account_exists"] is True
    for body in ({}, {"code": "000000"}):
        r = accept(anon, token, **body)
        assert (r.status_code, r.get_json()) == (401, {"error": "invalid_code"})
    r = accept(anon, token, code=pyotp.TOTP(secret).now())
    assert (r.status_code, r.get_json()) == (200, {"status": "accepted"})
    assert len(db_rows("SELECT 1 FROM staff_members WHERE organization_id = :o", o=staff.organization_id)) == 2
    assert db_rows("SELECT count(*) AS n FROM accounts")[0].n == 2
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE accounts SET totp_last_step = NULL"))
    me = login(
        client.application.test_client(),
        fake_email('new.person', 'clinic.example.test'),
        password=PASSWORD,
        organization_id=staff.organization_id,
        totp_secret=secret,
    )
    assert me


def test_existing_account_wrong_password_401(manager_in, client, anon, make_org, make_staff, make_account, db_rows):
    _, staff, headers = manager_in
    make_staff(make_org("Other"), make_account(fake_email('new.person', 'clinic.example.test'), password=PASSWORD))
    token = token_of(invite(client, headers, staff))
    r = accept(anon, token, password=fake_password('incorrect'))
    assert (r.status_code, r.get_json()) == (401, {"error": "invalid_credentials"})
    assert db_rows("SELECT status FROM invitations")[0].status == "pending"
    assert accept(anon, token).status_code == 200


def test_existing_staff_in_this_org_is_409_already_staff_at_accept(
    manager_in, client, anon, make_account, make_staff, db_rows
):
    org, staff, headers = manager_in
    token = token_of(invite(client, headers, staff))
    make_staff(org, make_account(fake_email('new.person', 'clinic.example.test'), password=PASSWORD), is_active=False)
    r = accept(anon, token)
    assert (r.status_code, r.get_json()) == (409, {"error": "already_staff"})
    assert db_rows("SELECT status FROM invitations")[0].status == "pending"


def test_accept_twice_410_used(manager_in, client, anon):
    _, staff, headers = manager_in
    token = token_of(invite(client, headers, staff))
    assert accept(anon, token).status_code == 200
    for r in (accept(anon, token), anon.get(f"/api/public/invitations/{token}")):
        assert (r.status_code, r.get_json()) == (410, {"error": "invitation_used"})


def test_expired_after_72_hours_410(manager_in, client, anon, owner_engine, db_rows):
    _, staff, headers = manager_in
    token = token_of(invite(client, headers, staff))
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE invitations SET expires_at = now() - interval '1 second'"))
    for r in (accept(anon, token), anon.get(f"/api/public/invitations/{token}")):
        assert (r.status_code, r.get_json()) == (410, {"error": "invitation_expired"})
    assert db_rows("SELECT status FROM invitations")[0].status == "pending"
    assert client.get("/api/invitations").get_json()["items"] == []
    assert invite(client, headers, staff).status_code == 201


def test_revoked_410(manager_in, client, anon, db_rows):
    _, staff, headers = manager_in
    r = invite(client, headers, staff)
    token, inv_id = token_of(r), r.get_json()["id"]
    assert client.delete(f"/api/invitations/{inv_id}", json={}, headers=headers).status_code == 204
    for resp in (accept(anon, token), anon.get(f"/api/public/invitations/{token}")):
        assert (resp.status_code, resp.get_json()) == (410, {"error": "invitation_revoked"})
    [audit] = db_rows("SELECT detail FROM audit_entries WHERE entity_type = 'invitation' AND action = 'update'")
    assert audit.detail == {"fields": ["status"]}
    assert client.delete(f"/api/invitations/{inv_id}", json={}, headers=headers).status_code == 204
    assert len(db_rows("SELECT 1 FROM audit_entries WHERE entity_type = 'invitation' AND action = 'update'")) == 1


def test_already_staff_and_already_invited_409(manager_in, client):
    _, staff, headers = manager_in
    r = invite(client, headers, staff, email=fake_email('MGR', 'clinic.example.test'))
    assert (r.status_code, r.get_json()) == (409, {"error": "already_staff"})
    assert invite(client, headers, staff).status_code == 201
    r = invite(client, headers, staff, email=fake_email('new.person', 'Clinic.example.test'))
    assert (r.status_code, r.get_json()) == (409, {"error": "already_invited"})


def test_clinic_ids_must_belong_to_the_organization(manager_in, client, make_org, make_clinic):
    _, staff, headers = manager_in
    foreign = make_clinic(make_org("Other"), "Elsewhere")
    r = invite(client, headers, staff, clinic_ids=[str(foreign.id)])
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["clinic_ids"]})
    for over in ({"roles": []}, {"roles": ["owner"]}, {"clinic_ids": []}):
        assert invite(client, headers, staff, **over).status_code == 422


def test_malformed_or_unknown_token_is_404(anon):
    for t in ("short", "x" * 43, "!" * 43, "a" * 200):
        assert anon.get(f"/api/public/invitations/{t}").status_code == 404
        assert accept(anon, t).status_code == 404


def test_receptionist_cannot_manage_invitations(client, login, csrf, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('rec', 'clinic.example.test'))
    login(client, fake_email('rec', 'clinic.example.test'))
    h = csrf(client)
    assert client.get("/api/invitations").status_code == 403
    body = {"email": fake_email('a', 'b.example.test'), "full_name": "A", "roles": ["dentist"], "clinic_ids": [str(uuid4())]}
    assert client.post("/api/invitations", json=body, headers=h).status_code == 403
    assert client.delete("/api/invitations/00000000-0000-0000-0000-000000000000", json={}, headers=h).status_code == 403


def test_invitation_of_another_organization_cannot_be_revoked(
    manager_in, client, make_org, make_staff, owner_engine, db_rows
):
    _, staff, headers = manager_in
    other = make_org("Other")
    boss = make_staff(other, fake_email('boss', 'other.example.test'))
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                f"""INSERT INTO invitations (id, organization_id, email, full_name, roles, clinic_ids, token_hash, status, expires_at, created_by_staff_member_id) SELECT gen_random_uuid(), :o, {fake_email("'a", 'b.example.test')}', 'A', ARRAY['dentist']::staff_role[], ARRAY[gen_random_uuid()], repeat('a', 64), 'pending', now() + interval '1 day', :s"""
            ),
            {"o": other.id, "s": boss.id},
        )
    [inv] = db_rows("SELECT id FROM invitations")
    assert client.delete(f"/api/invitations/{inv.id}", json={}, headers=headers).status_code == 404
    assert client.get("/api/invitations").get_json()["items"] == []


def test_concurrent_accepts_of_one_token_create_one_staff_member(manager_in, client, db_rows):
    from concurrent.futures import ThreadPoolExecutor

    _, staff, headers = manager_in
    token = token_of(invite(client, headers, staff))
    clients = [client.application.test_client() for _ in range(4)]
    with ThreadPoolExecutor(4) as pool:
        codes = sorted(pool.map(lambda c: accept(c, token).status_code, clients))
    assert codes == [200, 410, 410, 410]
    assert len(db_rows("SELECT 1 FROM staff_members WHERE full_name = 'New Person'")) == 1


def _fresh_token(client, headers, staff):
    r = invite(client, headers, staff)
    token = token_of(r)
    client.delete(f"/api/invitations/{r.get_json()['id']}", json={}, headers=headers)
    return token, r


def test_failed_accept_writes_login_failed_without_email(
    manager_in, client, anon, make_org, make_staff, make_account, db_rows
):
    _, staff, headers = manager_in
    secret = pyotp.random_base32()
    victim_org = make_org("Victim Clinic")
    make_staff(victim_org, make_account(fake_email('new.person', 'clinic.example.test'), password=PASSWORD, totp_secret=secret))
    token = token_of(invite(client, headers, staff))
    assert accept(anon, token, password=fake_password('incorrect')).status_code == 401
    assert accept(anon, token, code="000000").status_code == 401
    rows = db_rows(
        "SELECT organization_id, detail FROM audit_entries WHERE action = 'login_failed' ORDER BY occurred_at"
    )
    assert [r.detail for r in rows] == [{"via": "invitation"}, {"via": "invitation", "factor": "totp"}]
    assert {r.organization_id for r in rows} == {victim_org.id}
    assert "clinic.hr" not in str([r.detail for r in rows])


def test_account_created_meanwhile_race_code_is_documented():
    import json
    from pathlib import Path

    spec = json.loads((Path(__file__).resolve().parents[4] / "openapi.json").read_text(encoding="utf-8"))
    assert "409" in spec["paths"]["/api/public/invitations/{token}/accept"]["post"]["responses"]
