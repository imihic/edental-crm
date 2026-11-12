from testing import fake_email

from app.identity import Role


def test_expected_organization_rejects_stale_patient_reads_and_writes(
    client, login, csrf, make_account, make_org, make_staff
):
    account = make_account(fake_email('staff', 'com.example.test'))
    old_org, active_org = make_org("Old"), make_org("Active")
    make_staff(old_org, account, roles=(Role.RECEPTIONIST,))
    make_staff(active_org, account, roles=(Role.RECEPTIONIST,))
    login(client, fake_email('staff', 'com.example.test'), organization_id=old_org.id)
    assert client.post(
        "/api/auth/organization",
        json={"organization_id": str(active_org.id)},
        headers=csrf(client),
    ).status_code == 200

    stale = {"X-Expected-Organization": str(old_org.id)}
    for response in (
        client.get("/api/patients", headers=stale),
        client.post(
            "/api/patients",
            json={"first_name": "Testa", "last_name": "Testić"},
            headers={**csrf(client), **stale},
        ),
    ):
        assert (response.status_code, response.get_json()) == (409, {"error": "organization_changed"})

    matching = {"X-Expected-Organization": str(active_org.id)}
    for headers in ({}, matching):
        response = client.get("/api/patients", headers=headers)
        assert (response.status_code, response.get_json()) == (200, {"items": [], "total": 0})
    assert client.get("/api/auth/me", headers=stale).get_json()["organization"]["id"] == str(active_org.id)
