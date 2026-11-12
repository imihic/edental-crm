from datetime import UTC, date, datetime
from uuid import uuid4

OIB = "11111111119"


def test_detail_is_audited_and_masks_oib(client, signed_in, make_patient, audit_rows):
    org, staff, _ = signed_in
    p = make_patient(org, oib=OIB, date_of_birth=date(2015, 1, 1), phone_e164="+12025550100")
    r = client.get(f"/api/patients/{p.id}")
    out = r.get_json()
    assert r.status_code == 200 and out["oib_masked"] == "*******1119"
    assert OIB not in r.get_data(as_text=True)
    assert out["is_minor"] is True and isinstance(out["age"], int) and out["guardians"] == []
    assert out["preferred_clinic"] is None
    [e] = audit_rows()
    assert (e.action, e.entity_type, e.entity_id, e.staff_member_id) == ("view", "patient", p.id, staff.id)


def test_detail_without_birth_date_has_no_age(client, signed_in, make_patient):
    p = make_patient(signed_in[0])
    out = client.get(f"/api/patients/{p.id}").get_json()
    assert out["age"] is None and out["is_minor"] is False


def test_other_org_patient_is_404(client, signed_in, make_patient, make_org):
    p = make_patient(make_org("Other"))
    r = client.get(f"/api/patients/{p.id}")
    assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})
    assert client.get(f"/api/patients/{uuid4()}").status_code == 404


def test_retired_patient_is_410(client, signed_in, make_patient):
    kept = make_patient(signed_in[0], "Kept", "One")
    gone = make_patient(signed_in[0], "Gone", "Two", retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    r = client.get(f"/api/patients/{gone.id}")
    assert (r.status_code, r.get_json()) == (410, {"error": "merged", "merged_into": str(kept.id)})
