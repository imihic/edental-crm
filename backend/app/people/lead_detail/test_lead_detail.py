from testing import fake_email

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.people.models import Enquiry


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def test_detail_has_enquiries_newest_first_and_is_audited(client, signed_in, clinic, make_lead, owner_engine, audit_rows):
    org, staff, _ = signed_in
    lead = make_lead(org, clinic, "Testan Testač", email=fake_email('testan', 'x.example.test'))
    now = datetime.now(UTC)
    with Session(owner_engine) as s:
        for i, msg in enumerate(["first", "second"]):
            s.add(
                Enquiry(
                    organization_id=org.id, lead_id=lead.id, clinic_id=clinic.id, source="phone",
                    message=msg, received_at=now + timedelta(minutes=i),
                )
            )
        s.commit()
    r = client.get(f"/api/leads/{lead.id}")
    out = r.get_json()
    assert r.status_code == 200 and [e["message"] for e in out["enquiries"]] == ["second", "first"]
    assert out["converted_patient_id"] is None and out["possible_duplicates"] == []
    assert out["stage"] == "new" and out["full_name"] == "Testan Testač"
    [e] = audit_rows(entity_type="lead")
    assert (e.action, e.entity_id, e.staff_member_id) == ("view", lead.id, staff.id)


def test_possible_duplicates_by_email(client, signed_in, clinic, make_lead, make_patient):
    org = signed_in[0]
    lead = make_lead(org, clinic, "Testan Testač", email=fake_email('same', 'x.example.test'))
    p = make_patient(org, "Testan", "Testač", email=fake_email('SAME', 'x.example.test'))
    twin = make_lead(org, clinic, "I. Testac", email=fake_email('same', 'x.example.test'))
    make_lead(org, clinic, "Other", email=fake_email('other', 'x.example.test'))
    dups = client.get(f"/api/leads/{lead.id}").get_json()["possible_duplicates"]
    assert {(d["kind"], d["id"], tuple(d["reasons"])) for d in dups} == {
        ("patient", str(p.id), ("email",)),
        ("lead", str(twin.id), ("email",)),
    }


def test_other_org_is_404_and_unknown_is_404(client, signed_in, make_org, make_clinic, make_lead):
    org = make_org("Other")
    lead = make_lead(org, make_clinic(org, "X"))
    assert client.get(f"/api/leads/{lead.id}").status_code == 404
    assert client.get(f"/api/leads/{uuid4()}").status_code == 404


def test_retired_lead_is_410(client, signed_in, clinic, make_lead, make_patient):
    kept = make_patient(signed_in[0])
    gone = make_lead(signed_in[0], clinic, retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    r = client.get(f"/api/leads/{gone.id}")
    assert (r.status_code, r.get_json()) == (410, {"error": "merged", "merged_into": str(kept.id)})
