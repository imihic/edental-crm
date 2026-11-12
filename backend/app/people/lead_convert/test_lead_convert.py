from testing import fake_email

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.people import LeadConverted
from app.platform.events import subscribe

BODY = {"first_name": "Testan", "last_name": "Testač", "email": fake_email('testan', 'com.example.test')}


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def convert(client, headers, lead, **body):
    return client.post(f"/api/leads/{lead.id}/convert", json={**BODY, **body}, headers=headers)


def rows(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def seed_consents(engine, org, lead):
    base = datetime(2026, 1, 1, tzinfo=UTC)
    ids = {k: uuid4() for k in ("m1", "m2", "r1")}
    entries = [
        ("m1", "marketing", True, base),
        ("r1", "marketing", True, base + timedelta(days=1)),
        ("m2", "marketing", False, base + timedelta(days=2)),
    ]
    with engine.begin() as conn:
        for key, purpose, granted, at in entries:
            conn.execute(
                text(
                    "INSERT INTO consents (id, organization_id, lead_id, purpose, granted, source, recorded_at) "
                    "VALUES (:i, :o, :l, :p, :g, 'verbal', :t)"
                ),
                {"i": ids[key], "o": org.id, "l": lead.id, "p": purpose, "g": granted, "t": at},
            )
    return ids, base


def test_convert_creates_patient_and_carries_enquiries_and_consents(
    client, signed_in, clinic, make_lead, owner_engine, audit_rows
):
    org, staff, h = signed_in
    lead = make_lead(org, clinic, email=fake_email('testan', 'com.example.test'))
    with owner_engine.begin() as conn:
        for msg in ("one", "two"):
            conn.execute(
                text(
                    "INSERT INTO enquiries (id, organization_id, lead_id, clinic_id, source, message) "
                    "VALUES (:i, :o, :l, :c, 'phone', :m)"
                ),
                {"i": uuid4(), "o": org.id, "l": lead.id, "c": clinic.id, "m": msg},
            )
    ids, base = seed_consents(owner_engine, org, lead)
    r = convert(client, h, lead)
    assert r.status_code == 201, r.get_json()
    patient_id = r.get_json()["id"]
    assert r.get_json()["consent"]["marketing"] == "withdrawn"

    [lead_row] = rows(owner_engine, "SELECT stage, converted_patient_id FROM leads")
    assert (lead_row.stage, str(lead_row.converted_patient_id)) == ("converted", patient_id)
    enq = rows(owner_engine, "SELECT lead_id, patient_id FROM enquiries")
    assert len(enq) == 2 and all(e.lead_id == lead.id and str(e.patient_id) == patient_id for e in enq)

    copies = rows(
        owner_engine,
        "SELECT purpose, granted, source, carried_from_consent_id, recorded_by_staff_member_id, "
        "given_by_guardian_link_id, recorded_at FROM consents WHERE patient_id = :p ORDER BY recorded_at",
        p=patient_id,
    )
    assert [(c.purpose, c.granted, c.source, c.carried_from_consent_id) for c in copies] == [
        ("marketing", True, "conversion", ids["m1"]),
        ("marketing", True, "conversion", ids["r1"]),
        ("marketing", False, "conversion", ids["m2"]),
    ]
    assert [c.recorded_at for c in copies] == [base, base + timedelta(days=1), base + timedelta(days=2)]
    assert all(c.recorded_by_staff_member_id == staff.id and c.given_by_guardian_link_id is None for c in copies)
    assert len(rows(owner_engine, "SELECT 1 FROM consents WHERE lead_id = :l", l=lead.id)) == 3

    [created] = audit_rows("create")
    assert (str(created.entity_id), created.detail) == (patient_id, {})
    [updated] = audit_rows("update", entity_type="lead")
    assert (updated.entity_id, updated.detail) == (lead.id, {"fields": ["stage"]})
    detail = client.get(f"/api/leads/{lead.id}").get_json()
    assert detail["stage"] == "converted" and detail["converted_patient_id"] == patient_id


def test_convert_publishes_event_inside_transaction(client, signed_in, clinic, make_lead):
    org, _, h = signed_in
    lead = make_lead(org, clinic)
    seen = []
    subscribe(LeadConverted, lambda s, e: seen.append(e))
    r = convert(client, h, lead)
    assert r.status_code == 201
    assert len(seen) == 1
    assert (seen[0].organization_id, seen[0].lead_id, str(seen[0].patient_id)) == (org.id, lead.id, r.get_json()["id"])


def test_failing_subscriber_rolls_everything_back(client, signed_in, clinic, make_lead, owner_engine):
    org, _, h = signed_in
    lead = make_lead(org, clinic)
    seed_consents(owner_engine, org, lead)

    def boom(session, event):
        raise RuntimeError("subscriber failed")

    subscribe(LeadConverted, boom)
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    r = convert(client, h, lead)
    assert r.status_code == 500
    assert rows(owner_engine, "SELECT 1 FROM patients") == []
    assert rows(owner_engine, "SELECT 1 FROM consents WHERE patient_id IS NOT NULL") == []
    [lead_row] = rows(owner_engine, "SELECT stage, converted_patient_id FROM leads")
    assert (lead_row.stage, lead_row.converted_patient_id) == ("new", None)
    assert rows(owner_engine, "SELECT 1 FROM audit_entries WHERE entity_type IN ('patient', 'lead')") == []


def test_convert_twice_is_409(client, signed_in, clinic, make_lead, owner_engine):
    org, _, h = signed_in
    lead = make_lead(org, clinic)
    assert convert(client, h, lead).status_code == 201
    r = convert(client, h, lead)
    assert (r.status_code, r.get_json()) == (409, {"error": "invalid_transition"})
    assert len(rows(owner_engine, "SELECT 1 FROM patients")) == 1


def test_convert_from_lost_stage_is_allowed(client, signed_in, clinic, make_lead):
    lead = make_lead(signed_in[0], clinic, stage="lost", lost_reason="price")
    assert convert(client, signed_in[2], lead).status_code == 201


def test_convert_warns_on_existing_patient_duplicate(client, signed_in, clinic, make_lead, make_patient, owner_engine):
    org, _, h = signed_in
    twin = make_patient(org, "Testan", "Testač", email=fake_email('testan', 'com.example.test'))
    lead = make_lead(org, clinic, email=fake_email('testan', 'com.example.test'))
    r = convert(client, h, lead)
    assert r.status_code == 409 and r.get_json()["error"] == "possible_duplicates"
    assert [(d["kind"], d["id"]) for d in r.get_json()["duplicates"]] == [("patient", str(twin.id))]
    assert len(rows(owner_engine, "SELECT 1 FROM patients")) == 1
    [lead_row] = rows(owner_engine, "SELECT stage, converted_patient_id FROM leads")
    assert (lead_row.stage, lead_row.converted_patient_id) == ("new", None)
    assert rows(owner_engine, "SELECT 1 FROM audit_entries WHERE action = 'update'") == []
    assert convert(client, h, lead, confirm_duplicates=True).status_code == 201


def test_convert_does_not_report_the_lead_itself_as_duplicate(client, signed_in, clinic, make_lead):
    lead = make_lead(signed_in[0], clinic, email=fake_email('testan', 'com.example.test'))
    assert convert(client, signed_in[2], lead).status_code == 201


def test_convert_still_warns_about_another_lead_with_same_email(client, signed_in, clinic, make_lead):
    org, _, h = signed_in
    other = make_lead(org, clinic, "Testo Testač", email=fake_email('testan', 'com.example.test'))
    lead = make_lead(org, clinic, email=fake_email('testan', 'com.example.test'))
    r = convert(client, h, lead)
    assert r.status_code == 409
    assert [(d["kind"], d["id"]) for d in r.get_json()["duplicates"]] == [("lead", str(other.id))]


def test_convert_oib_taken_and_invalid_write_nothing(client, signed_in, clinic, make_lead, make_patient, owner_engine):
    org, _, h = signed_in
    make_patient(org, "Testa", "Baka", oib="11111111119")
    lead = make_lead(org, clinic)
    assert convert(client, h, lead, oib="11111111119").get_json() == {"error": "oib_taken"}
    r = convert(client, h, lead, oib="123")
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["oib"]})
    [lead_row] = rows(owner_engine, "SELECT stage FROM leads")
    assert lead_row.stage == "new"


def test_convert_retired_410_unknown_and_other_org_404(
    client, signed_in, clinic, make_lead, make_patient, make_org, make_clinic
):
    org, _, h = signed_in
    kept = make_patient(org)
    retired = make_lead(org, clinic, retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    r = convert(client, h, retired)
    assert (r.status_code, r.get_json()) == (410, {"error": "merged", "merged_into": str(kept.id)})
    other = make_org("Other")
    foreign = make_lead(other, make_clinic(other, "X"))
    assert convert(client, h, foreign).status_code == 404
    assert client.post(f"/api/leads/{uuid4()}/convert", json=BODY, headers=h).status_code == 404


def test_convert_requires_login(client, signed_in, clinic, make_lead):
    lead = make_lead(signed_in[0], clinic)
    anon = client.application.test_client()
    assert anon.post(f"/api/leads/{lead.id}/convert", json=BODY).status_code in (401, 403)
