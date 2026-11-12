from testing import fake_email

import pytest
from sqlalchemy import text


@pytest.fixture
def anon(app):
    return app.test_client()


@pytest.fixture
def form(client, manager_in, owner_engine):
    org, _, _ = manager_in
    with owner_engine.connect() as conn:
        cid = conn.execute(text("SELECT id FROM clinics WHERE name = 'Centar'")).scalar_one()
    key = client.get(f"/api/clinics/{cid}/enquiry-form").get_json()["key"]
    return org, cid, key


def payload(**over):
    base = {
        "full_name": "Testm Testnovak",
        "phone": "00 1 202 555 0100",
        "email": fake_email('testm', 'x.example.test'),
        "message": "Do you do whitening?",
        "marketing_consent": True,
    }
    return {**base, **over}


def rows(owner_engine, sql, **params):
    with owner_engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def submit(client, key, **over):
    return client.post(f"/api/public/enquiry-forms/{key}/enquiries", json=payload(**over))


def test_public_info_exposes_only_names(anon, form):
    r = anon.get(f"/api/public/enquiry-forms/{form[2]}")
    assert (r.status_code, r.get_json()) == (
        200,
        {"clinic_name": "Centar", "organization_name": "Smile", "locale": "en"},
    )


def test_public_endpoints_need_no_session_or_csrf(anon, form, owner_engine):
    r = submit(anon, form[2])
    assert (r.status_code, r.get_json()) == (202, {"status": "received"})
    non_json = anon.post(f"/api/public/enquiry-forms/{form[2]}/enquiries", data="x=1")
    assert non_json.status_code == 415


def test_public_submit_creates_lead_with_consent(anon, form, owner_engine, audit_rows):
    org, cid, key = form
    r = submit(anon, key, preferred_contact_time="evenings")
    assert (r.status_code, r.get_json()) == (202, {"status": "received"})
    [lead] = rows(owner_engine, "SELECT id, phone_e164, clinic_id, organization_id FROM leads")
    assert (lead.phone_e164, lead.clinic_id, lead.organization_id) == ("+12025550100", cid, org.id)
    [enq] = rows(
        owner_engine,
        "SELECT lead_id, source, created_by_staff_member_id, preferred_contact_time FROM enquiries",
    )
    assert (enq.lead_id, enq.source, enq.created_by_staff_member_id, enq.preferred_contact_time) == (
        lead.id,
        "website_form",
        None,
        "evenings",
    )
    [c] = rows(
        owner_engine,
        "SELECT lead_id, patient_id, purpose, granted, source, recorded_by_staff_member_id FROM consents",
    )
    assert (c.lead_id, c.patient_id, c.purpose, c.granted, c.source, c.recorded_by_staff_member_id) == (
        lead.id,
        None,
        "marketing",
        True,
        "enquiry_form",
        None,
    )
    [e] = audit_rows(entity_type="enquiry")
    assert (e.action, e.staff_member_id, e.detail) == ("create", None, {"source": "website_form"})


def test_no_marketing_consent_writes_no_consent_row(anon, form, owner_engine):
    assert submit(anon, form[2], marketing_consent=False).status_code == 202
    assert rows(owner_engine, "SELECT 1 FROM consents") == []
    assert len(rows(owner_engine, "SELECT 1 FROM leads")) == 1


def test_public_submit_known_patient_email_attaches_without_writing_consent(anon, form, make_patient, owner_engine):
    org, _, key = form
    p = make_patient(org, email=fake_email('testm', 'x.example.test'))
    r = submit(anon, key)
    assert (r.status_code, r.get_json()) == (202, {"status": "received"})
    assert rows(owner_engine, "SELECT 1 FROM leads") == []
    [enq] = rows(owner_engine, "SELECT patient_id, lead_id, marketing_consent_requested FROM enquiries")
    assert (enq.patient_id, enq.lead_id, enq.marketing_consent_requested) == (p.id, None, True)
    assert rows(owner_engine, "SELECT 1 FROM consents") == []


def test_enquiry_flag_false_when_not_requested_and_exposed_to_staff(client, anon, form, make_patient, owner_engine):
    org, _, key = form
    p = make_patient(org, email=fake_email('testm', 'x.example.test'))
    submit(anon, key, marketing_consent=False)
    submit(anon, key, marketing_consent=True)
    items = client.get(f"/api/patients/{p.id}/enquiries").get_json()["items"]
    assert sorted(i["marketing_consent_requested"] for i in items) == [False, True]


def test_lead_enquiry_records_flag_too(anon, form, owner_engine):
    submit(anon, form[2])
    [enq] = rows(owner_engine, "SELECT marketing_consent_requested FROM enquiries")
    assert enq.marketing_consent_requested is True


def test_signed_in_manager_of_another_organization_submits_to_the_form_owner(
    client, form, make_org, make_clinic, owner_engine
):
    org_a = form[0]
    org_b = make_org("Other")
    clinic_b = make_clinic(org_b, "Branch")
    key_b = "B" * 32
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO enquiry_forms (id, organization_id, clinic_id, key) VALUES (gen_random_uuid(), :o, :c, :k)"),
            {"o": org_b.id, "c": clinic_b.id, "k": key_b},
        )
    assert submit(client, key_b).status_code == 202
    [lead] = rows(owner_engine, "SELECT organization_id, clinic_id FROM leads")
    assert (lead.organization_id, lead.clinic_id) == (org_b.id, clinic_b.id)
    assert rows(owner_engine, "SELECT 1 FROM leads WHERE organization_id = :o", o=org_a.id) == []
    for sql in ("SELECT organization_id FROM enquiries", "SELECT organization_id FROM audit_entries WHERE entity_type = 'enquiry'"):
        assert {r.organization_id for r in rows(owner_engine, sql)} == {org_b.id}


def test_honeypot_discards(anon, form, owner_engine):
    r = submit(anon, form[2], website="http://spam.example")
    assert (r.status_code, r.get_json()) == (202, {"status": "received"})
    for table in ("leads", "enquiries", "consents", "audit_entries"):
        assert rows(owner_engine, f"SELECT 1 FROM {table} WHERE entity_type = 'enquiry'" if table == "audit_entries" else f"SELECT 1 FROM {table}") == []


def test_validation_names_fields_and_never_echoes_values(anon, form, owner_engine):
    r = submit(anon, form[2], phone="not-a-phone-secret", email=None)
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["phone"]})
    assert b"secret" not in r.data
    r = submit(anon, form[2], phone=None, email=None)
    assert r.status_code == 422 and set(r.get_json()["fields"]) == {"phone", "email"}
    r = submit(anon, form[2], email="bad-secret-email")
    assert r.status_code == 422 and r.get_json()["fields"] == ["email"] and b"secret" not in r.data
    assert rows(owner_engine, "SELECT 1 FROM enquiries") == []


@pytest.mark.parametrize("state", ["unknown", "regenerated", "disabled", "bad_format", "short"])
def test_disabled_or_unknown_key_404(anon, form, owner_engine, state):
    _, _, key = form
    if state == "regenerated":
        with owner_engine.begin() as conn:
            conn.execute(text("UPDATE enquiry_forms SET key = 'Z' || substr(key, 2), rotated_at = now()"))
        key = form[2]
    elif state == "disabled":
        with owner_engine.begin() as conn:
            conn.execute(text("UPDATE enquiry_forms SET enabled = false"))
    elif state == "unknown":
        key = "a" * 32
    elif state == "bad_format":
        key = key[:31] + "!"
    else:
        key = "abc"
    for r in (anon.get(f"/api/public/enquiry-forms/{key}"), submit(anon, key)):
        assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})
    assert rows(owner_engine, "SELECT 1 FROM leads") == []


def test_old_key_404_after_regenerate(client, anon, form, manager_in, owner_engine):
    _, cid, old = form
    new = client.post(f"/api/clinics/{cid}/enquiry-form/regenerate", json={}, headers=manager_in[2]).get_json()["key"]
    assert anon.get(f"/api/public/enquiry-forms/{old}").status_code == 404
    assert submit(anon, old).status_code == 404
    assert anon.get(f"/api/public/enquiry-forms/{new}").status_code == 200
    assert rows(owner_engine, "SELECT 1 FROM enquiries") == []


def test_signed_in_staff_browser_can_use_public_form_without_csrf(client, form):
    assert submit(client, form[2]).status_code == 202
    assert client.get(f"/api/public/enquiry-forms/{form[2]}").status_code == 200
