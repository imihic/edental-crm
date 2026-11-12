from testing import fake_email

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text


def add(client, h, patient_id, **body):
    return client.post(f"/api/patients/{patient_id}/guardians", json=body, headers=h)


def test_add_patient_guardian_and_contact_guardian(client, signed_in, make_patient, audit_rows):
    org, staff, h = signed_in
    child = make_patient(org, "Mali", "Testić")
    mum = make_patient(org, "Testg", "Testić", phone_e164="+12025550100", email=fake_email('m', 'x.example.test'))
    r = add(client, h, child.id, relationship="parent", guardian_patient_id=str(mum.id))
    assert r.status_code == 201, r.get_json()
    out = r.get_json()
    assert (out["kind"], out["guardian_id"], out["relationship"]) == ("patient", str(mum.id), "parent")
    assert (out["display_name"], out["phone"], out["email"]) == ("Testg Testić", "+12025550100", fake_email('m', 'x.example.test'))
    r = add(client, h, child.id, relationship="other", contact={"full_name": "Baka  Testa", "phone": "00 1 202 555 0100"})
    assert r.status_code == 201, r.get_json()
    out = r.get_json()
    assert (out["kind"], out["display_name"], out["phone"], out["email"]) == (
        "contact",
        "Baka Testa",
        "+12025550100",
        None,
    )
    updates = audit_rows("update")
    assert len(updates) == 2
    assert all(e.detail == {"fields": ["guardians"]} and e.entity_id == child.id for e in updates)


def test_guardian_cannot_be_self(client, signed_in, make_patient):
    org, _, h = signed_in
    p = make_patient(org)
    r = add(client, h, p.id, relationship="parent", guardian_patient_id=str(p.id))
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["guardian_patient_id"]})


def test_exactly_one_guardian_kind_required(client, signed_in, make_patient):
    org, _, h = signed_in
    p, q = make_patient(org), make_patient(org, "Q", "Q")
    assert add(client, h, p.id, relationship="parent").status_code == 422
    both = add(client, h, p.id, relationship="parent", guardian_patient_id=str(q.id), contact={"full_name": "X"})
    assert both.status_code == 422
    assert add(client, h, p.id, relationship="bogus", guardian_patient_id=str(q.id)).status_code == 422


def test_invalid_contact_phone_and_email(client, signed_in, make_patient):
    org, _, h = signed_in
    p = make_patient(org)
    r = add(client, h, p.id, relationship="other", contact={"full_name": "X", "phone": "abc"})
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["contact.phone"]})
    r = add(client, h, p.id, relationship="other", contact={"full_name": "X", "email": "nope"})
    assert r.status_code == 422


def test_same_guardian_twice_is_409(client, signed_in, make_patient):
    org, _, h = signed_in
    p, q = make_patient(org), make_patient(org, "Q", "Q")
    assert add(client, h, p.id, relationship="parent", guardian_patient_id=str(q.id)).status_code == 201
    r = add(client, h, p.id, relationship="other", guardian_patient_id=str(q.id))
    assert (r.status_code, r.get_json()) == (409, {"error": "guardian_exists"})


def test_cross_org_guardian_patient_rejected(client, signed_in, make_patient, make_org):
    org, _, h = signed_in
    p = make_patient(org)
    foreign = make_patient(make_org("Other"))
    r = add(client, h, p.id, relationship="parent", guardian_patient_id=str(foreign.id))
    assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})
    assert add(client, h, foreign.id, relationship="parent", guardian_patient_id=str(p.id)).status_code == 404
    assert add(client, h, p.id, relationship="parent", guardian_patient_id=str(uuid4())).status_code == 404


def test_retired_guardian_is_410(client, signed_in, make_patient):
    org, _, h = signed_in
    p, kept = make_patient(org), make_patient(org, "Kept", "K")
    gone = make_patient(org, "Gone", "G", retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    r = add(client, h, p.id, relationship="parent", guardian_patient_id=str(gone.id))
    assert (r.status_code, r.get_json()) == (410, {"error": "merged", "merged_into": str(kept.id)})
    r = add(client, h, gone.id, relationship="parent", guardian_patient_id=str(kept.id))
    assert r.status_code == 410


def test_detail_lists_guardians_and_guardian_of(client, signed_in, make_patient):
    org, _, h = signed_in
    child, mum = make_patient(org, "Mali", "Testić"), make_patient(org, "Testg", "Testić")
    link = add(client, h, child.id, relationship="parent", guardian_patient_id=str(mum.id)).get_json()
    add(client, h, child.id, relationship="other", contact={"full_name": "Baka Testa"})
    out = client.get(f"/api/patients/{child.id}").get_json()
    assert {(g["kind"], g["display_name"]) for g in out["guardians"]} == {
        ("patient", "Testg Testić"),
        ("contact", "Baka Testa"),
    }
    assert out["guardian_of"] == []
    mum_out = client.get(f"/api/patients/{mum.id}").get_json()
    assert mum_out["guardian_of"] == [{"patient_id": str(child.id), "display_name": "Mali Testić"}]
    assert link["id"] in {g["id"] for g in out["guardians"]}


def test_remove_guardian(client, signed_in, make_patient, audit_rows, owner_engine):
    org, _, h = signed_in
    p, q = make_patient(org), make_patient(org, "Q", "Q")
    link = add(client, h, p.id, relationship="parent", guardian_patient_id=str(q.id)).get_json()
    r = client.delete(f"/api/patients/{p.id}/guardians/{link["id"]}", json={}, headers=h)
    assert r.status_code == 204
    assert client.get(f"/api/patients/{p.id}").get_json()["guardians"] == []
    assert len(audit_rows("update")) == 2
    assert client.delete(f"/api/patients/{p.id}/guardians/{link["id"]}", json={}, headers=h).status_code == 404
    with owner_engine.connect() as conn:
        assert conn.execute(
            text("SELECT ended_at FROM guardian_links WHERE id = :id"), {"id": link["id"]}
        ).scalar_one() is not None


def test_cannot_remove_link_of_another_patient(client, signed_in, make_patient):
    org, _, h = signed_in
    p, q, third = make_patient(org), make_patient(org, "Q", "Q"), make_patient(org, "R", "R")
    link = add(client, h, p.id, relationship="parent", guardian_patient_id=str(q.id)).get_json()
    assert client.delete(f"/api/patients/{third.id}/guardians/{link["id"]}", json={}, headers=h).status_code == 404


def test_guardian_tables_have_expected_grants(owner_engine):
    with owner_engine.connect() as conn:

        def has(table, priv):
            return conn.execute(
                text("SELECT has_table_privilege('crm_app', :t, :p)"), {"t": f"public.{table}", "p": priv}
            ).scalar_one()

        assert [has("contacts", p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE")] == [True, True, True, False]
        assert [has("guardian_links", p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE")] == [True, True, False, True]
        assert conn.execute(
            text("SELECT has_column_privilege('crm_app', 'guardian_links', 'ended_at', 'UPDATE')")
        ).scalar_one()
