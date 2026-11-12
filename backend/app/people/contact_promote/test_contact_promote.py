from datetime import date
from uuid import uuid4

from sqlalchemy import text


def make_contact(owner_engine, org, name="Baka Testa"):
    cid = uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO contacts (id, organization_id, full_name) VALUES (:i, :o, :n)"),
            {"i": cid, "o": org.id, "n": name},
        )
    return cid


def test_promote_contact_moves_links(client, signed_in, make_patient, owner_engine, audit_rows):
    org, staff, h = signed_in
    child = make_patient(org, "Mali", "Testić")
    other_child = make_patient(org, "Drugi", "Testić")
    contact = make_contact(owner_engine, org)
    with owner_engine.begin() as conn:
        for pid, rel in ((child.id, "parent"), (other_child.id, "other")):
            conn.execute(
                text(
                    "INSERT INTO guardian_links (id, organization_id, patient_id, guardian_contact_id, relationship) "
                    "VALUES (:i, :o, :p, :c, :r)"
                ),
                {"i": uuid4(), "o": org.id, "p": pid, "c": contact, "r": rel},
            )
    r = client.post(
        f"/api/contacts/{contact}/promote",
        json={"first_name": "Testa", "last_name": "Baka", "phone": "00 1 202 555 0100"},
        headers=h,
    )
    assert r.status_code == 201, r.get_json()
    new_id = r.get_json()["id"]
    assert r.get_json()["phone"] == "+12025550100"
    with owner_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT patient_id, guardian_patient_id, guardian_contact_id, relationship FROM guardian_links")
        ).all()
        assert conn.execute(text("SELECT count(*) FROM contacts WHERE id = :c"), {"c": contact}).scalar_one() == 1
    assert {(x.patient_id, str(x.guardian_patient_id), x.guardian_contact_id, x.relationship) for x in rows} == {
        (child.id, new_id, None, "parent"),
        (other_child.id, new_id, None, "other"),
    }
    detail = client.get(f"/api/patients/{child.id}").get_json()
    assert [(g["kind"], g["guardian_id"]) for g in detail["guardians"]] == [("patient", new_id)]
    assert len(client.get(f"/api/patients/{new_id}").get_json()["guardian_of"]) == 2
    [entry] = audit_rows("create")
    assert str(entry.entity_id) == new_id and entry.detail == {}


def test_promotion_moves_consent_link_but_leaves_ended_link(client, signed_in, make_patient, owner_engine):
    org, _, h = signed_in
    child = make_patient(org, "Mali", "Testić")
    link = client.post(
        f"/api/patients/{child.id}/guardians",
        json={"relationship": "parent", "contact": {"full_name": "Baka Testa"}},
        headers=h,
    )
    assert link.status_code == 201, link.get_json()
    active_id, contact_id = link.get_json()["id"], link.get_json()["guardian_id"]
    ended_id = uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO guardian_links (id, organization_id, patient_id, guardian_contact_id, relationship, "
                "ended_at) VALUES (:i, :o, :p, :c, 'parent', now())"
            ),
            {"i": ended_id, "o": org.id, "p": child.id, "c": contact_id},
        )
    consents_url = f"/api/patients/{child.id}/consents"
    consent = client.post(
        consents_url,
        json={"purpose": "marketing", "granted": True, "source": "verbal", "given_by_guardian_link_id": active_id},
        headers=h,
    )
    assert consent.status_code == 201, consent.get_json()

    promoted = client.post(
        f"/api/contacts/{contact_id}/promote", json={"first_name": "Testa", "last_name": "Baka"}, headers=h
    )
    assert promoted.status_code == 201, promoted.get_json()
    (active,) = client.get(f"/api/patients/{child.id}").get_json()["guardians"]
    assert (active["id"], active["kind"], active["guardian_id"]) == (active_id, "patient", promoted.get_json()["id"])
    with owner_engine.connect() as conn:
        ended = conn.execute(
            text("SELECT guardian_contact_id, ended_at FROM guardian_links WHERE id = :id"), {"id": ended_id}
        ).one()
    assert str(ended.guardian_contact_id) == contact_id and ended.ended_at is not None
    assert client.get(consents_url).get_json()["history"] == [consent.get_json()]


def test_contact_can_only_be_promoted_once(client, signed_in, owner_engine, audit_rows):
    org, _, h = signed_in
    contact = make_contact(owner_engine, org)
    url = f"/api/contacts/{contact}/promote"
    body = {"first_name": "Testa", "last_name": "Baka", "confirm_duplicates": True}
    first = client.post(url, json=body, headers=h)
    assert first.status_code == 201, first.get_json()
    repeated = client.post(url, json=body, headers=h)
    assert (repeated.status_code, repeated.get_json()) == (409, {"error": "contact_already_promoted"})
    [entry] = audit_rows("create")
    assert str(entry.entity_id) == first.get_json()["id"]


def test_promote_duplicate_needs_confirmation(client, signed_in, make_patient, owner_engine):
    org, _, h = signed_in
    make_patient(org, "Testa", "Baka", oib="11111111119")
    contact = make_contact(owner_engine, org)
    body = {"first_name": "Testa", "last_name": "Baka", "oib": "11111111119"}
    r = client.post(f"/api/contacts/{contact}/promote", json=body, headers=h)
    assert (r.status_code, r.get_json()) == (409, {"error": "oib_taken"})
    dup = {"first_name": "Testa", "last_name": "Baka", "date_of_birth": "1990-01-01"}
    make_patient(org, "Testa", "Baka", date_of_birth=date(1990, 1, 1))
    r = client.post(f"/api/contacts/{contact}/promote", json=dup, headers=h)
    assert r.status_code == 409 and r.get_json()["error"] == "possible_duplicates"
    r = client.post(f"/api/contacts/{contact}/promote", json={**dup, "confirm_duplicates": True}, headers=h)
    assert r.status_code == 201


def test_promote_unknown_or_other_org_contact_is_404(client, signed_in, make_org, owner_engine):
    _, _, h = signed_in
    foreign = make_contact(owner_engine, make_org("Other"))
    body = {"first_name": "A", "last_name": "B"}
    assert client.post(f"/api/contacts/{foreign}/promote", json=body, headers=h).status_code == 404
    assert client.post(f"/api/contacts/{uuid4()}/promote", json=body, headers=h).status_code == 404


def test_promote_invalid_body_is_422(client, signed_in, owner_engine):
    org, _, h = signed_in
    contact = make_contact(owner_engine, org)
    body = {"first_name": "A", "last_name": "B", "oib": "123"}
    r = client.post(f"/api/contacts/{contact}/promote", json=body, headers=h)
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["oib"]})
