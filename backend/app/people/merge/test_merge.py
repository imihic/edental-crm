from testing import fake_email

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.identity import Role
from app.people import RecordsMerged
from app.platform.events import subscribe

OIB_A = "11111111119"


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def merge(client, headers, kept, kind, retired, **choices):
    return client.post(
        f"/api/patients/{kept.id}/merge",
        json={"retired_kind": kind, "retired_id": str(retired.id), "field_choices": choices},
        headers=headers,
    )


def rows(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def run(engine, sql, **params):
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def add_link(engine, org, child, guardian_patient=None, contact=None, rel="parent"):
    link_id = uuid4()
    run(
        engine,
        "INSERT INTO guardian_links (id, organization_id, patient_id, guardian_patient_id, guardian_contact_id, "
        "relationship) VALUES (:i, :o, :p, :g, :c, :r)",
        i=link_id,
        o=org.id,
        p=child.id,
        g=guardian_patient.id if guardian_patient else None,
        c=contact,
        r=rel,
    )
    return link_id


def add_contact(engine, org):
    cid = uuid4()
    run(engine, "INSERT INTO contacts (id, organization_id, full_name) VALUES (:i, :o, 'Baka')", i=cid, o=org.id)
    return cid


def add_consent(engine, org, *, patient=None, lead=None, granted=True, at=None, link=None):
    cid = uuid4()
    run(
        engine,
        "INSERT INTO consents (id, organization_id, patient_id, lead_id, purpose, granted, source, recorded_at, "
        "given_by_guardian_link_id) VALUES (:i, :o, :p, :l, 'marketing', :g, 'verbal', :t, :k)",
        i=cid,
        o=org.id,
        p=patient.id if patient else None,
        l=lead.id if lead else None,
        g=granted,
        t=at or datetime(2026, 1, 1, tzinfo=UTC),
        k=link,
    )
    return cid


def add_enquiry(engine, org, clinic, *, patient=None, lead=None):
    run(
        engine,
        "INSERT INTO enquiries (id, organization_id, lead_id, patient_id, clinic_id, source, message) "
        "VALUES (:i, :o, :l, :p, :c, 'phone', 'hi')",
        i=uuid4(),
        o=org.id,
        l=lead.id if lead else None,
        p=patient.id if patient else None,
        c=clinic.id,
    )


def test_merge_patient_moves_everything_and_retires(
    client, signed_in, clinic, make_patient, owner_engine, audit_rows
):
    org, staff, h = signed_in
    kept = make_patient(org, "Testa", "Testić")
    retired = make_patient(org, "Testa", "Testić", email=fake_email('testa', 'x.example.test'))
    child = make_patient(org, "Mali", "Testić")
    mom = make_patient(org, "Testg", "Testić")
    contact = add_contact(owner_engine, org)
    add_enquiry(owner_engine, org, clinic, patient=retired)
    add_enquiry(owner_engine, org, clinic, patient=retired)
    dup_link = add_link(owner_engine, org, retired, guardian_patient=mom)
    add_link(owner_engine, org, kept, guardian_patient=mom)
    contact_link = add_link(owner_engine, org, retired, contact=contact)
    guardian_link = add_link(owner_engine, org, child, guardian_patient=retired)
    self_link = add_link(owner_engine, org, kept, guardian_patient=retired)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2026, 2, 1, tzinfo=UTC)
    c_old = add_consent(owner_engine, org, patient=retired, at=base, granted=True)
    c_new = add_consent(owner_engine, org, patient=retired, at=later, granted=False)
    add_consent(owner_engine, org, patient=child, at=base, link=guardian_link)

    r = merge(client, h, kept, "patient", retired)
    assert r.status_code == 200, r.get_json()
    out = r.get_json()
    assert out["id"] == str(kept.id) and out["consent"]["marketing"] == "withdrawn"
    assert {g["guardian_id"] for g in out["guardians"]} == {str(mom.id), str(contact)}
    assert [g["patient_id"] for g in out["guardian_of"]] == [str(child.id)]

    [ret] = rows(owner_engine, "SELECT retired_into_patient_id, retired_at FROM patients WHERE id = :i", i=retired.id)
    assert ret.retired_into_patient_id == kept.id and ret.retired_at is not None
    assert all(e.patient_id == kept.id for e in rows(owner_engine, "SELECT patient_id FROM enquiries"))
    links = {x.id: x for x in rows(owner_engine, "SELECT id, patient_id, guardian_patient_id FROM guardian_links")}
    assert links[contact_link].patient_id == kept.id
    assert links[guardian_link].guardian_patient_id == kept.id and links[guardian_link].patient_id == child.id
    assert links[dup_link].patient_id == retired.id
    assert links[self_link].guardian_patient_id == retired.id
    copies = rows(
        owner_engine,
        "SELECT granted, source, carried_from_consent_id, recorded_by_staff_member_id, recorded_at, "
        "given_by_guardian_link_id FROM consents WHERE patient_id = :p ORDER BY recorded_at",
        p=kept.id,
    )
    assert [(c.granted, c.source, c.carried_from_consent_id, c.recorded_by_staff_member_id, c.recorded_at) for c in copies] == [
        (True, "merge", c_old, staff.id, base),
        (False, "merge", c_new, staff.id, later),
    ]
    assert all(c.given_by_guardian_link_id is None for c in copies)

    [upd] = audit_rows("update")
    assert upd.entity_id == kept.id and upd.detail == {"fields": ["merged"]}
    [dele] = audit_rows("delete")
    assert dele.entity_id == retired.id and dele.detail == {"merged_into": str(kept.id)}


@pytest.mark.parametrize("retired_is_guardian", [False, True])
def test_merge_moves_active_links_past_ended_links(client, signed_in, make_patient, owner_engine, retired_is_guardian):
    org, _, h = signed_in
    kept, retired, other = (make_patient(org, name, "Testić") for name in ("Testa", "Anamarija", "Testg"))
    source = (other, retired) if retired_is_guardian else (retired, other)
    target = (other, kept) if retired_is_guardian else (kept, other)
    ended_source = add_link(owner_engine, org, *source)
    ended_target = add_link(owner_engine, org, *target)
    for link_id in (ended_source, ended_target):
        run(owner_engine, "UPDATE guardian_links SET ended_at = now() WHERE id = :i", i=link_id)
    active = add_link(owner_engine, org, *source)

    r = merge(client, h, kept, "patient", retired)
    assert r.status_code == 200, r.get_json()
    links = {
        link.id: (link.patient_id, link.guardian_patient_id, link.ended_at is not None)
        for link in rows(owner_engine, "SELECT id, patient_id, guardian_patient_id, ended_at FROM guardian_links")
    }
    assert links == {
        ended_source: (source[0].id, source[1].id, True),
        ended_target: (target[0].id, target[1].id, True),
        active: (target[0].id, target[1].id, False),
    }


def test_field_choices_pick_values(client, signed_in, make_patient, owner_engine, audit_rows):
    org, _, h = signed_in
    kept = make_patient(org, "Testa", "Testić", phone_e164="+12025550102", address="Kept st", notes="kept note")
    retired = make_patient(
        org,
        "Anamarija",
        "Testić",
        oib=OIB_A,
        phone_e164="+12025550103",
        email=fake_email('r', 'x.example.test'),
        address="Retired st",
        date_of_birth=date(2000, 1, 2),
        preferred_language="en",
    )
    r = merge(
        client,
        h,
        kept,
        "patient",
        retired,
        first_name="retired",
        oib="retired",
        phone="retired",
        email="retired",
        date_of_birth="retired",
        address="kept",
        preferred_language="retired",
    )
    assert r.status_code == 200, r.get_json()
    out = r.get_json()
    assert (out["first_name"], out["phone"], out["email"], out["address"], out["notes"], out["preferred_language"]) == (
        "Anamarija",
        "+12025550103",
        fake_email('r', 'x.example.test'),
        "Kept st",
        "kept note",
        "en",
    )
    assert out["date_of_birth"] == "2000-01-02" and out["oib_masked"]
    [k] = rows(owner_engine, "SELECT oib FROM patients WHERE id = :i", i=kept.id)
    [x] = rows(owner_engine, "SELECT oib, retired_at FROM patients WHERE id = :i", i=retired.id)
    assert k.oib == OIB_A and x.oib is None and x.retired_at is not None
    [upd] = audit_rows("update")
    assert upd.detail == {
        "fields": ["address", "date_of_birth", "email", "first_name", "oib", "phone", "preferred_language", "merged"]
    }


@pytest.mark.parametrize("choices", [{"stage": "retired"}, {"id": "kept"}, {"phone": "other"}, {"first_name": "yes"}])
def test_bad_field_choices_are_422(client, signed_in, make_patient, choices, owner_engine):
    org, _, h = signed_in
    kept, retired = make_patient(org, "A", "B"), make_patient(org, "A", "B")
    r = merge(client, h, kept, "patient", retired, **choices)
    assert r.status_code == 422
    assert rows(owner_engine, "SELECT retired_at FROM patients WHERE id = :i", i=retired.id)[0].retired_at is None


def test_unknown_field_names_field_choices(client, signed_in, make_patient):
    org, _, h = signed_in
    kept, retired = make_patient(org, "A", "B"), make_patient(org, "A", "B")
    r = merge(client, h, kept, "patient", retired, stage="retired")
    assert r.get_json() == {"error": "validation_error", "fields": ["field_choices"]}


def test_merge_lead_into_patient(client, signed_in, clinic, make_patient, make_lead, owner_engine, audit_rows):
    org, staff, h = signed_in
    kept = make_patient(org, "Testan", "Testač", phone_e164="+12025550102")
    lead = make_lead(org, clinic, email=fake_email('l', 'x.example.test'), phone_e164="+12025550104", stage="contacted")
    add_enquiry(owner_engine, org, clinic, lead=lead)
    at = datetime(2026, 3, 1, tzinfo=UTC)
    c = add_consent(owner_engine, org, lead=lead, at=at)
    r = merge(client, h, kept, "lead", lead, phone="retired", email="retired")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["phone"] == "+12025550104" and r.get_json()["email"] == fake_email('l', 'x.example.test')
    assert r.get_json()["consent"]["marketing"] == "granted"
    [row] = rows(owner_engine, "SELECT stage, retired_into_patient_id, retired_at FROM leads")
    assert (row.stage, row.retired_into_patient_id) == ("contacted", kept.id) and row.retired_at is not None
    [e] = rows(owner_engine, "SELECT lead_id, patient_id FROM enquiries")
    assert e.patient_id == kept.id
    [copy] = rows(
        owner_engine, "SELECT source, carried_from_consent_id, recorded_at FROM consents WHERE patient_id = :p", p=kept.id
    )
    assert (copy.source, copy.carried_from_consent_id, copy.recorded_at) == ("merge", c, at)
    [dele] = audit_rows("delete", "lead")
    assert dele.entity_id == lead.id and dele.detail == {"merged_into": str(kept.id)}
    [upd] = audit_rows("update")
    assert upd.detail == {"fields": ["email", "phone", "merged"]}
    gone = client.get(f"/api/leads/{lead.id}")
    assert gone.status_code == 410 and gone.get_json() == {"error": "merged", "merged_into": str(kept.id)}


def test_lead_merge_only_allows_phone_and_email(client, signed_in, clinic, make_patient, make_lead):
    org, _, h = signed_in
    kept, lead = make_patient(org), make_lead(org, clinic, email=fake_email('l', 'x.example.test'))
    r = merge(client, h, kept, "lead", lead, first_name="retired")
    assert r.status_code == 422 and r.get_json()["fields"] == ["field_choices"]


def test_cannot_merge_patient_into_lead(client, signed_in, clinic, make_patient, make_lead):
    org, _, h = signed_in
    patient, lead = make_patient(org), make_lead(org, clinic, email=fake_email('l', 'x.example.test'))
    r = client.post(
        f"/api/patients/{lead.id}/merge",
        json={"retired_kind": "patient", "retired_id": str(patient.id), "field_choices": {}},
        headers=h,
    )
    assert r.status_code == 404


def test_invalid_merges_are_409(client, signed_in, make_patient):
    org, _, h = signed_in
    a, b, c = make_patient(org, "A", "A"), make_patient(org, "B", "B"), make_patient(org, "C", "C")
    r = merge(client, h, a, "patient", a)
    assert (r.status_code, r.get_json()["error"]) == (409, "invalid_merge")
    assert merge(client, h, a, "patient", b).status_code == 200
    r = merge(client, h, c, "patient", b)
    assert (r.status_code, r.get_json()["error"]) == (409, "invalid_merge")
    r = merge(client, h, b, "patient", c)
    assert (r.status_code, r.get_json()["error"]) == (409, "invalid_merge")


def test_unknown_retired_record_is_404(client, signed_in, make_patient):
    org, _, h = signed_in
    kept = make_patient(org)
    r = client.post(
        f"/api/patients/{kept.id}/merge",
        json={"retired_kind": "lead", "retired_id": str(uuid4()), "field_choices": {}},
        headers=h,
    )
    assert r.status_code == 404


def test_retired_detail_is_410_with_merged_into(client, signed_in, make_patient):
    org, _, h = signed_in
    kept, retired = make_patient(org, "A", "A"), make_patient(org, "B", "B")
    assert merge(client, h, kept, "patient", retired).status_code == 200
    r = client.get(f"/api/patients/{retired.id}")
    assert r.status_code == 410 and r.get_json() == {"error": "merged", "merged_into": str(kept.id)}


def test_retired_absent_from_list_search_duplicates_and_counts(
    client, signed_in, clinic, make_patient, make_lead, owner_engine
):
    org, _, h = signed_in
    kept = make_patient(org, "Testa", "Testzoric")
    retired = make_patient(org, "Testa", "Testzoric", email=fake_email('dup', 'x.example.test'), oib=OIB_A, date_of_birth=date(1990, 1, 1))
    other = make_patient(org, "Testp", "Peric")
    lead = make_lead(org, clinic, "Lea Lead", email=fake_email('dup', 'x.example.test'))
    lead2 = make_lead(org, clinic, "Lea Two", email=fake_email('lea2', 'x.example.test'))
    target = make_patient(org, "Testiva", "Ivic")
    add_link(owner_engine, org, other, guardian_patient=retired)
    add_link(owner_engine, org, retired, guardian_patient=other)
    assert client.get("/api/leads").get_json()["counts"]["new"] == 2

    assert merge(client, h, kept, "patient", retired).status_code == 200
    assert merge(client, h, target, "lead", lead2).status_code == 200

    listing = client.get("/api/patients").get_json()
    assert listing["total"] == 3 and str(retired.id) not in str(listing)
    assert client.get(fake_email('/api/patients?q=dup', 'x.example.test')).get_json()["total"] == 0
    assert client.get(f"/api/patients?q={OIB_A}").get_json()["total"] == 0
    leads = client.get("/api/leads").get_json()
    assert leads["total"] == 1 and leads["counts"]["new"] == 1
    assert client.get("/api/leads?q=Two").get_json()["total"] == 0
    r = client.post(
        "/api/patients",
        json={"first_name": "Testa", "last_name": "Testzoric", "date_of_birth": "1990-01-01", "email": fake_email('dup', 'x.example.test'), "oib": OIB_A},
        headers=h,
    )
    assert r.status_code == 409 and [d["id"] for d in r.get_json()["duplicates"]] == [str(lead.id)]
    assert client.get(f"/api/leads/{lead.id}").get_json()["possible_duplicates"] == []
    detail = client.get(f"/api/patients/{other.id}").get_json()
    assert str(retired.id) not in str(detail["guardians"]) + str(detail["guardian_of"])
    mid = make_patient(org, "Testev", "Eric", email=fake_email('only', 'x.example.test'))
    assert merge(client, h, kept, "patient", mid).status_code == 200
    r = client.post(
        "/api/leads",
        json={"full_name": "Testev E", "email": fake_email('only', 'x.example.test'), "clinic_id": str(clinic.id), "source": "phone", "message": "hi"},
        headers=h,
    )
    assert r.status_code == 201 and r.get_json()["attached_to"] == "lead"


def test_guardians_of_excludes_retired_guardian_left_behind(client, signed_in, make_patient, owner_engine):
    org, _, h = signed_in
    child, guardian, kept = make_patient(org, "C", "C"), make_patient(org, "G", "G"), make_patient(org, "K", "K")
    add_link(owner_engine, org, child, guardian_patient=guardian)
    add_link(owner_engine, org, child, guardian_patient=kept)
    assert merge(client, h, kept, "patient", guardian).status_code == 200
    guardians = client.get(f"/api/patients/{child.id}").get_json()["guardians"]
    assert [g["guardian_id"] for g in guardians] == [str(kept.id)]


def _other_client(app, make_staff, login, csrf, org, email, roles):
    make_staff(org, email, roles=roles)
    c = app.test_client()
    login(c, email)
    return c, csrf(c)


def test_dentist_cannot_merge(app, signed_in, make_patient, make_staff, login, csrf):
    org, _, _ = signed_in
    kept, retired = make_patient(org, "A", "A"), make_patient(org, "B", "B")
    c, h = _other_client(app, make_staff, login, csrf, org, fake_email('dent', 'clinic.example.test'), (Role.DENTIST,))
    r = merge(c, h, kept, "patient", retired)
    assert (r.status_code, r.get_json()["error"]) == (403, "forbidden")


def test_merge_publishes_event(client, signed_in, clinic, make_patient, make_lead):
    org, _, h = signed_in
    seen = []
    subscribe(RecordsMerged, lambda session, event: seen.append(event))
    kept, retired = make_patient(org, "A", "A"), make_patient(org, "B", "B")
    lead = make_lead(org, clinic, email=fake_email('l', 'x.example.test'))
    merge(client, h, kept, "patient", retired)
    merge(client, h, kept, "lead", lead)
    assert seen == [
        RecordsMerged(organization_id=org.id, kept_patient_id=kept.id, retired_kind="patient", retired_id=retired.id),
        RecordsMerged(organization_id=org.id, kept_patient_id=kept.id, retired_kind="lead", retired_id=lead.id),
    ]


def test_failed_merge_publishes_nothing(client, signed_in, make_patient):
    org, _, h = signed_in
    seen = []
    subscribe(RecordsMerged, lambda session, event: seen.append(event))
    a = make_patient(org)
    merge(client, h, a, "patient", a)
    assert seen == []
