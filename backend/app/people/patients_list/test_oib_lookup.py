from datetime import UTC, datetime


OIB = "11111111119"


def test_exact_oib_lookup_matches_active_patient_without_returning_the_oib(client, signed_in, make_patient, audit_rows):
    organization, staff, headers = signed_in
    patient = make_patient(organization, oib=OIB)
    response = client.post("/api/patients/lookup-oib", json={"oib": OIB}, headers=headers)
    assert (response.status_code, response.get_json()) == (200, {"patient_id": str(patient.id)})
    assert OIB not in response.get_data(as_text=True)
    [entry] = audit_rows("view", entity_type="patient")
    assert (entry.entity_id, entry.staff_member_id, entry.detail) == (
        patient.id, staff.id, {"field": "oib", "operation": "lookup"},
    )


def test_exact_oib_lookup_ignores_retired_and_other_organization_patients(client, signed_in, make_patient, make_org):
    organization, _, headers = signed_in
    replacement = make_patient(organization)
    make_patient(organization, oib=OIB, retired_at=datetime.now(UTC), retired_into_patient_id=replacement.id)
    make_patient(make_org("Other"), oib=OIB)
    response = client.post("/api/patients/lookup-oib", json={"oib": OIB}, headers=headers)
    assert (response.status_code, response.get_json()) == (200, {"patient_id": None})


def test_exact_oib_lookup_rejects_invalid_checksums_and_requires_csrf(client, signed_in):
    invalid = client.post("/api/patients/lookup-oib", json={"oib": "11111111110"}, headers=signed_in[2])
    assert (invalid.status_code, invalid.get_json()) == (422, {"error": "validation_error", "fields": ["oib"]})
    assert client.post("/api/patients/lookup-oib", json={"oib": OIB}).status_code == 403
