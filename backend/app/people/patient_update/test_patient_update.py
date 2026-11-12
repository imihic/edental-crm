from testing import fake_email

from datetime import UTC, datetime

OIB = "11111111119"


def test_update_records_changed_field_names_only(client, signed_in, make_patient, audit_rows):
    p = make_patient(signed_in[0], "Testa", "Testić", email=fake_email('a', 'x.example.test'))
    r = client.patch(
        f"/api/patients/{p.id}",
        json={"last_name": "Testač", "email": fake_email('a', 'x.example.test'), "notes": "secret"},
        headers=signed_in[2],
    )
    assert r.status_code == 200 and r.get_json()["last_name"] == "Testač"
    [e] = audit_rows("update")
    assert e.detail == {"fields": ["last_name", "notes"]}


def test_update_validates_and_clears(client, signed_in, make_patient):
    p = make_patient(signed_in[0], phone_e164="+12025550100")
    h = signed_in[2]
    bad = client.patch(f"/api/patients/{p.id}", json={"oib": "11111111110"}, headers=h)
    assert (bad.status_code, bad.get_json()["fields"]) == (422, ["oib"])
    bad = client.patch(f"/api/patients/{p.id}", json={"first_name": None}, headers=h)
    assert bad.status_code == 422
    ok = client.patch(f"/api/patients/{p.id}", json={"phone": None, "oib": OIB}, headers=h)
    assert ok.get_json()["phone"] is None and ok.get_json()["oib_masked"] == "*******1119"


def test_update_oib_uniqueness(client, signed_in, make_patient):
    make_patient(signed_in[0], "Other", "Person", oib=OIB)
    p = make_patient(signed_in[0])
    r = client.patch(f"/api/patients/{p.id}", json={"oib": OIB}, headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (409, {"error": "oib_taken"})


def test_update_keeping_own_oib_is_fine(client, signed_in, make_patient):
    p = make_patient(signed_in[0], oib=OIB)
    r = client.patch(f"/api/patients/{p.id}", json={"oib": OIB, "notes": "x"}, headers=signed_in[2])
    assert r.status_code == 200


def test_update_other_org_and_retired(client, signed_in, make_patient, make_org):
    other = make_patient(make_org("Other"))
    assert client.patch(f"/api/patients/{other.id}", json={"notes": "x"}, headers=signed_in[2]).status_code == 404
    kept = make_patient(signed_in[0], "Kept", "One")
    gone = make_patient(signed_in[0], "Gone", "Two", retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    assert client.patch(f"/api/patients/{gone.id}", json={"notes": "x"}, headers=signed_in[2]).status_code == 410


def test_oib_race_maps_to_oib_taken_not_500(client, signed_in, make_patient, monkeypatch):
    make_patient(signed_in[0], "Other", "Person", oib=OIB)
    p = make_patient(signed_in[0])
    monkeypatch.setattr("app.people.patient_update.route.oib_taken", lambda *a, **k: False)
    r = client.patch(f"/api/patients/{p.id}", json={"oib": OIB}, headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (409, {"error": "oib_taken"})


def test_update_validates_email_and_birth_date(client, signed_in, make_patient):
    p = make_patient(signed_in[0])
    h = signed_in[2]
    r = client.patch(f"/api/patients/{p.id}", json={"email": "nope"}, headers=h)
    assert (r.status_code, r.get_json()["fields"]) == (422, ["email"])
    r = client.patch(f"/api/patients/{p.id}", json={"date_of_birth": "2999-01-01"}, headers=h)
    assert (r.status_code, r.get_json()["fields"]) == (422, ["date_of_birth"])
