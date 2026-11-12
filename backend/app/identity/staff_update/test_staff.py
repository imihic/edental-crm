from testing import fake_email

import pytest

from app.identity import Role


@pytest.fixture
def team(manager_in, make_staff, make_account):
    org, mgr, headers = manager_in
    rec = make_staff(
        org,
        make_account(fake_email('rec', 'clinic.example.test')),
        roles=(Role.RECEPTIONIST,),
        full_name="Testr",
        clinics=(mgr.clinics_by_name["Zapad"],),
    )
    return org, mgr, rec, headers


def test_manager_lists_and_updates_staff(client, team, db_rows):
    org, mgr, rec, headers = team
    items = client.get("/api/staff").get_json()["items"]
    assert {i["email"] for i in items} == {fake_email('mgr', 'clinic.example.test'), fake_email('rec', 'clinic.example.test')}
    testr = next(i for i in items if i["email"] == fake_email('rec', 'clinic.example.test'))
    assert testr == {
        "id": str(rec.id),
        "full_name": "Testr",
        "email": fake_email('rec', 'clinic.example.test'),
        "roles": ["receptionist"],
        "clinics": [{"id": str(mgr.clinics_by_name["Zapad"].id), "name": "Zapad"}],
        "is_active": True,
    }
    centar = mgr.clinics_by_name["Centar"]
    r = client.patch(
        f"/api/staff/{rec.id}",
        json={"full_name": "Testr K", "roles": ["dentist", "receptionist"], "clinic_ids": [str(centar.id)]},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["clinics"] == [{"id": str(centar.id), "name": "Centar"}]
    assert sorted(r.get_json()["roles"]) == ["dentist", "receptionist"] and r.get_json()["full_name"] == "Testr K"
    [a] = db_rows("SELECT detail FROM audit_entries WHERE entity_type = 'staff_member' AND action = 'update'")
    assert a.detail == {"fields": ["full_name", "roles", "clinic_ids"]}
    assert len(db_rows("SELECT 1 FROM staff_clinics WHERE staff_member_id = :i", i=rec.id)) == 1


def test_patch_rejects_email_account_and_foreign_clinics(client, team, make_org, make_clinic):
    _, mgr, rec, headers = team
    for body in (
        {"email": fake_email('x', 'y.example.test')},
        {"account_id": str(mgr.account_id)},
        {"roles": []},
        {"clinic_ids": []},
        {"roles": ["owner"]},
    ):
        assert client.patch(f"/api/staff/{rec.id}", json=body, headers=headers).status_code == 422
    foreign = make_clinic(make_org("Other"), "Elsewhere")
    r = client.patch(f"/api/staff/{rec.id}", json={"clinic_ids": [str(foreign.id)]}, headers=headers)
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["clinic_ids"]})
    r = client.patch("/api/staff/00000000-0000-0000-0000-000000000000", json={"full_name": "x"}, headers=headers)
    assert r.status_code == 404


def test_last_manager_cannot_be_removed_or_deactivated(client, team, make_staff, make_account):
    org, mgr, rec, headers = team
    r = client.patch(f"/api/staff/{mgr.id}", json={"roles": ["dentist"]}, headers=headers)
    assert (r.status_code, r.get_json()) == (409, {"error": "last_manager"})
    r = client.patch(f"/api/staff/{mgr.id}", json={"is_active": False}, headers=headers)
    assert (r.status_code, r.get_json()) == (409, {"error": "last_manager"})
    make_staff(org, make_account(fake_email('old', 'clinic.example.test')), roles=(Role.CLINIC_MANAGER,), is_active=False)
    assert client.patch(f"/api/staff/{mgr.id}", json={"is_active": False}, headers=headers).status_code == 409
    assert client.patch(f"/api/staff/{mgr.id}", json={"full_name": "Boss"}, headers=headers).status_code == 200
    assert client.patch(f"/api/staff/{rec.id}", json={"roles": ["clinic_manager"]}, headers=headers).status_code == 200
    assert client.patch(f"/api/staff/{mgr.id}", json={"roles": ["dentist"]}, headers=headers).status_code == 200


def test_deactivated_staff_session_is_revoked(client, team, login):
    _, _, rec, headers = team
    other = client.application.test_client()
    login(other, fake_email('rec', 'clinic.example.test'))
    assert other.get("/api/auth/me").status_code == 200
    assert client.patch(f"/api/staff/{rec.id}", json={"is_active": False}, headers=headers).status_code == 200
    assert other.get("/api/auth/me").status_code == 401


def test_receptionist_cannot_manage_staff(client, login, csrf, make_org, make_staff):
    org = make_org("Smile")
    boss = make_staff(org, fake_email('boss', 'clinic.example.test'), roles=(Role.CLINIC_MANAGER,))
    make_staff(org, fake_email('rec', 'clinic.example.test'))
    login(client, fake_email('rec', 'clinic.example.test'))
    assert client.get("/api/staff").status_code == 403
    r = client.patch(f"/api/staff/{boss.id}", json={"full_name": "x"}, headers=csrf(client))
    assert r.status_code == 403


def test_concurrent_demotions_cannot_remove_both_managers(client, team, login, make_staff, make_account, db_rows):
    from concurrent.futures import ThreadPoolExecutor

    import pyotp

    org, mgr, rec, headers = team
    secret = pyotp.random_base32()
    second = make_staff(org, make_account(fake_email('two', 'clinic.example.test'), totp_secret=secret), roles=(Role.CLINIC_MANAGER,))
    other = client.application.test_client()
    login(other, fake_email('two', 'clinic.example.test'), totp_secret=secret)
    h2 = {"X-CSRF-Token": other.get("/api/auth/csrf").get_json()["csrf_token"]}
    jobs = [(client, headers, mgr.id), (other, h2, second.id)]
    with ThreadPoolExecutor(2) as pool:
        codes = sorted(
            pool.map(lambda j: j[0].patch(f"/api/staff/{j[2]}", json={"roles": ["dentist"]}, headers=j[1]).status_code, jobs)
        )
    assert codes in ([200, 409], [200, 403])
    assert len(db_rows("SELECT 1 FROM staff_members WHERE is_active AND 'clinic_manager' = ANY(roles::text[]::staff_role[])")) == 1
