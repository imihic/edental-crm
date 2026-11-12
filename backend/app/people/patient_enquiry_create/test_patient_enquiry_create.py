from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def payload(clinic, **over):
    return {"clinic_id": str(clinic.id), "source": "walk_in", "message": "Wants a check-up", **over}


def test_creates_enquiry_for_patient_and_audits(client, signed_in, clinic, make_patient, owner_engine, audit_rows):
    org, staff, headers = signed_in
    p = make_patient(org)
    r = client.post(f"/api/patients/{p.id}/enquiries", json=payload(clinic, preferred_contact_time="mornings"), headers=headers)
    out = r.get_json()
    assert r.status_code == 201 and out["patient_id"] == str(p.id) and out["lead_id"] is None
    assert out["preferred_contact_time"] == "mornings" and out["source"] == "walk_in"
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM leads")).scalar_one() == 0
    [e] = audit_rows(entity_type="enquiry")
    assert (e.action, str(e.entity_id), e.staff_member_id, e.detail) == ("create", out["id"], staff.id, {})


def test_other_org_clinic_is_422(client, signed_in, make_patient, make_org, make_clinic):
    p = make_patient(signed_in[0])
    foreign = make_clinic(make_org("Other"), "Foreign")
    r = client.post(f"/api/patients/{p.id}/enquiries", json=payload(foreign), headers=signed_in[2])
    assert (r.status_code, r.get_json()["fields"]) == (422, ["clinic_id"])


def test_validation_404_410(client, signed_in, clinic, make_patient, make_org):
    org, _, headers = signed_in
    p = make_patient(org)
    assert client.post(f"/api/patients/{p.id}/enquiries", json=payload(clinic, message=" "), headers=headers).status_code == 422
    assert client.post(f"/api/patients/{p.id}/enquiries", json=payload(clinic, source="website_form"), headers=headers).status_code == 422
    assert client.post(f"/api/patients/{uuid4()}/enquiries", json=payload(clinic), headers=headers).status_code == 404
    foreign = make_patient(make_org("Other"))
    assert client.post(f"/api/patients/{foreign.id}/enquiries", json=payload(clinic), headers=headers).status_code == 404
    gone = make_patient(org, "Gone", "X", retired_at=datetime.now(UTC), retired_into_patient_id=p.id)
    r = client.post(f"/api/patients/{gone.id}/enquiries", json=payload(clinic), headers=headers)
    assert (r.status_code, r.get_json()) == (410, {"error": "merged", "merged_into": str(p.id)})


def test_history_includes_converted_and_direct_enquiries(
    client, signed_in, clinic, make_clinic, make_org, make_patient, audit_rows
):
    org, staff, headers = signed_in
    second_clinic = make_clinic(org, "Sjever")
    lead = client.post(
        "/api/leads", headers=headers,
        json=payload(second_clinic, full_name="Test Patient", phone="+12025550105", message="Before conversion"),
    )
    assert lead.status_code == 201
    converted = client.post(
        f"/api/leads/{lead.get_json()['lead_id']}/convert", headers=headers,
        json={"first_name": "Test", "last_name": "Patient"},
    )
    assert converted.status_code == 201
    patient_id = converted.get_json()["id"]
    history_url = f"/api/patients/{patient_id}/enquiries"
    direct = client.post(history_url, json=payload(clinic, message="After conversion"), headers=headers)
    assert direct.status_code == 201

    first_page = client.get(history_url, query_string={"page_size": 1})
    second_page = client.get(history_url, query_string={"page_size": 1, "page": 2})
    assert first_page.status_code == second_page.status_code == 200
    assert first_page.get_json() == {"items": [direct.get_json()], "total": 2}
    assert second_page.get_json()["total"] == 2
    [carried] = second_page.get_json()["items"]
    assert (carried["message"], carried["clinic_id"], carried["patient_id"]) == (
        "Before conversion", str(second_clinic.id), patient_id,
    )
    foreign = make_patient(make_org("Other"))
    assert client.get(f"/api/patients/{foreign.id}/enquiries").status_code == 404
    assert client.get(history_url, query_string={"page_size": 101}).status_code == 422
    assert all(
        (str(entry.entity_id), entry.staff_member_id, entry.detail) == (patient_id, staff.id, {"field": "enquiries"})
        for entry in audit_rows("view", entity_type="patient")
    )
    assert len(audit_rows("view", entity_type="patient")) == 2
