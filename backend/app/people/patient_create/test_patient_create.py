from testing import fake_email

from datetime import UTC, date, datetime

OIB = "11111111119"


def body(**kw):
    return {"first_name": "Testana", "last_name": "Těstić", **kw}


def test_create_patient_normalizes_phone_and_audits(client, signed_in, audit_rows):
    org, staff, h = signed_in
    r = client.post("/api/patients", json=body(phone="00 1/202-555-0100", oib=OIB, email=fake_email('I', 'x.example.test')), headers=h)
    assert r.status_code == 201, r.get_json()
    out = r.get_json()
    assert out["phone"] == "+12025550100"
    assert out["oib_masked"] == "*******1119" and "oib" not in out
    assert out["preferred_language"] == "en" and out["guardians"] == [] and out["is_minor"] is False
    [entry] = audit_rows()
    assert (entry.action, str(entry.entity_id), entry.staff_member_id) == ("create", out["id"], staff.id)
    assert entry.detail == {}


def test_create_rejects_invalid_oib(client, signed_in):
    r = client.post("/api/patients", json=body(oib="11111111110"), headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["oib"]})


def test_create_rejects_invalid_phone(client, signed_in):
    r = client.post("/api/patients", json=body(phone="abc"), headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["phone"]})


def test_create_rejects_foreign_clinic(client, signed_in, make_org, make_clinic):
    other = make_clinic(make_org("Other"), "X")
    r = client.post("/api/patients", json=body(preferred_clinic_id=str(other.id)), headers=signed_in[2])
    assert (r.status_code, r.get_json()["fields"]) == (422, ["preferred_clinic_id"])


def test_create_with_preferred_clinic(client, signed_in, make_clinic):
    clinic = make_clinic(signed_in[0], "Centar")
    r = client.post("/api/patients", json=body(preferred_clinic_id=str(clinic.id)), headers=signed_in[2])
    assert r.status_code == 201
    assert r.get_json()["preferred_clinic"] == {"id": str(clinic.id), "name": "Centar"}


def test_create_warns_on_name_and_birth_date_duplicate(client, signed_in, make_patient):
    existing = make_patient(signed_in[0], "Testana", "Testic", date_of_birth=date(1990, 1, 2))
    r = client.post("/api/patients", json=body(date_of_birth="1990-01-02"), headers=signed_in[2])
    assert r.status_code == 409
    assert r.get_json() == {
        "error": "possible_duplicates",
        "duplicates": [
            {
                "kind": "patient",
                "id": str(existing.id),
                "display_name": "Testana Testic",
                "reasons": ["name_and_birth_date"],
            }
        ],
    }


def test_create_with_confirm_duplicates_succeeds(client, signed_in, make_patient):
    make_patient(signed_in[0], "Testana", "Testic", date_of_birth=date(1990, 1, 2))
    r = client.post(
        "/api/patients", json=body(date_of_birth="1990-01-02", confirm_duplicates=True), headers=signed_in[2]
    )
    assert r.status_code == 201


def test_shared_phone_is_not_a_duplicate(client, signed_in, make_patient):
    make_patient(signed_in[0], "Testk", "Testic", phone_e164="+12025550100")
    r = client.post("/api/patients", json=body(phone="0012025550100"), headers=signed_in[2])
    assert r.status_code == 201


def test_retired_patient_is_not_a_duplicate(client, signed_in, make_patient):
    kept = make_patient(signed_in[0], "Kept", "One")
    make_patient(
        signed_in[0], "Testana", "Testic", email=fake_email('i', 'x.example.test'), retired_at=datetime.now(UTC), retired_into_patient_id=kept.id
    )
    r = client.post("/api/patients", json=body(email=fake_email('i', 'x.example.test')), headers=signed_in[2])
    assert r.status_code == 201


def test_oib_taken_cannot_be_confirmed(client, signed_in, make_patient):
    make_patient(signed_in[0], "Other", "Person", oib=OIB)
    r = client.post("/api/patients", json=body(oib=OIB, confirm_duplicates=True), headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (409, {"error": "oib_taken"})


def test_same_oib_in_another_org_is_fine(client, signed_in, make_patient, make_org):
    make_patient(make_org("Other"), oib=OIB)
    assert client.post("/api/patients", json=body(oib=OIB), headers=signed_in[2]).status_code == 201


def test_patients_require_login(client):
    assert client.get("/api/patients").status_code == 401


def test_create_validates_email_and_birth_date(client, signed_in):
    h = signed_in[2]
    r = client.post("/api/patients", json=body(email="not-an-email"), headers=h)
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["email"]})
    r = client.post("/api/patients", json=body(date_of_birth="2999-01-01"), headers=h)
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["date_of_birth"]})


def test_oib_race_maps_to_oib_taken_not_500(client, signed_in, make_patient, monkeypatch):
    make_patient(signed_in[0], "Other", "Person", oib=OIB)
    monkeypatch.setattr("app.people.patient_service.oib_taken", lambda *a, **k: False)
    r = client.post("/api/patients", json=body(oib=OIB, confirm_duplicates=True), headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (409, {"error": "oib_taken"})


def test_same_surname_without_birth_date_match_is_not_reported(client, signed_in, make_patient):
    make_patient(signed_in[0], "Testk", "Testic", date_of_birth=date(1980, 5, 5))
    make_patient(signed_in[0], "Testana", "Testic", date_of_birth=date(1990, 1, 2))
    r = client.post("/api/patients", json=body(date_of_birth="1990-01-02"), headers=signed_in[2])
    assert r.status_code == 409
    assert [d["display_name"] for d in r.get_json()["duplicates"]] == ["Testana Testic"]
    assert client.post("/api/patients", json=body(), headers=signed_in[2]).status_code == 201


def _crowd(org, make_patient):
    for i in range(60):
        make_patient(org, f"Crowd{i}", "Testić", date_of_birth=date(1950, 1, 1 + i % 28), email=fake_email(f"c{i}", "x.example.test"))


def test_duplicate_found_among_many_same_surname_patients(client, signed_in, make_patient):
    _crowd(signed_in[0], make_patient)
    true = make_patient(signed_in[0], "Testa", "Testić", date_of_birth=date(1990, 1, 2))
    r = client.post(
        "/api/patients",
        json={"first_name": "Testa", "last_name": "Testić", "date_of_birth": "1990-01-02"},
        headers=signed_in[2],
    )
    assert r.status_code == 409
    assert [(d["id"], d["reasons"]) for d in r.get_json()["duplicates"]] == [
        (str(true.id), ["name_and_birth_date"])
    ]


def test_email_duplicate_found_among_many_same_surname_patients(client, signed_in, make_patient):
    _crowd(signed_in[0], make_patient)
    true = make_patient(signed_in[0], "Zed", "Other", email=fake_email('Real', 'x.example.test'))
    r = client.post(
        "/api/patients",
        json={"first_name": "Testa", "last_name": "Testić", "date_of_birth": "1950-01-01", "email": fake_email('real', 'x.example.test')},
        headers=signed_in[2],
    )
    assert r.status_code == 409
    assert [d["id"] for d in r.get_json()["duplicates"]][0] == str(true.id)


def test_patient_create_warns_about_lead_with_same_email(client, signed_in, make_clinic, make_lead):
    org, _, headers = signed_in
    lead = make_lead(org, make_clinic(org, "C"), "Testa Testić", email=fake_email('testa', 'x.example.test'))
    payload = {"first_name": "Testa", "last_name": "Testić", "email": fake_email('TESTA', 'x.example.test')}
    r = client.post("/api/patients", json=payload, headers=headers)
    assert r.status_code == 409 and r.get_json()["duplicates"] == [
        {"kind": "lead", "id": str(lead.id), "display_name": "Testa Testić", "reasons": ["email"]}
    ]
    assert client.post("/api/patients", json={**payload, "confirm_duplicates": True}, headers=headers).status_code == 201
