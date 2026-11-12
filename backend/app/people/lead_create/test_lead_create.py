from testing import fake_email

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.people.lead_create.handler import record_enquiry
from app.platform.db import set_tenant_context


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def body(clinic, **over):
    base = {
        "full_name": "Testan Testač",
        "phone": "00 1 202 555 0100",
        "clinic_id": str(clinic.id),
        "source": "phone",
        "message": "Do you do implants?",
    }
    return {**base, **over}


def rows(owner_engine, sql, **params):
    with owner_engine.connect() as conn:
        return conn.execute(text(sql), params).all()


def test_enquiry_from_unknown_person_creates_lead(client, signed_in, clinic, owner_engine, audit_rows):
    org, staff, headers = signed_in
    r = client.post("/api/leads", json=body(clinic, email=fake_email('new', 'x.example.test')), headers=headers)
    out = r.get_json()
    assert r.status_code == 201 and out["attached_to"] == "lead" and "patient_id" not in out
    [lead] = rows(owner_engine, "SELECT id, stage, phone_e164, full_name FROM leads")
    assert lead.id == UUID(out["lead_id"]) and lead.stage == "new" and lead.phone_e164 == "+12025550100"
    [enq] = rows(owner_engine, "SELECT lead_id, patient_id, source, created_by_staff_member_id FROM enquiries")
    assert (enq.lead_id, enq.patient_id, enq.source, enq.created_by_staff_member_id) == (lead.id, None, "phone", staff.id)
    [e] = audit_rows(entity_type="lead")
    assert (e.action, e.entity_id, e.detail) == ("create", lead.id, {})


def test_enquiry_from_known_patient_email_attaches_to_patient(client, signed_in, clinic, make_patient, owner_engine, audit_rows):
    org, _, headers = signed_in
    p = make_patient(org, email=fake_email('Testa', 'Clinic.example.test'))
    r = client.post("/api/leads", json=body(clinic, email=fake_email('testa', 'clinic.example.test')), headers=headers)
    assert r.status_code == 201 and r.get_json() == {"attached_to": "patient", "patient_id": str(p.id)}
    assert rows(owner_engine, "SELECT 1 FROM leads") == []
    [enq] = rows(owner_engine, "SELECT id, patient_id, lead_id FROM enquiries")
    assert (enq.patient_id, enq.lead_id) == (p.id, None)
    [e] = audit_rows(entity_type="enquiry")
    assert (e.action, e.entity_id) == ("create", enq.id)


def test_ambiguous_email_creates_lead(client, signed_in, clinic, make_patient, owner_engine):
    org, _, headers = signed_in
    make_patient(org, "Testa", "Testić", email=fake_email('shared', 'x.example.test'))
    make_patient(org, "Testo", "Testić", email=fake_email('shared', 'x.example.test'))
    r = client.post("/api/leads", json=body(clinic, email=fake_email('shared', 'x.example.test')), headers=headers)
    assert r.get_json()["attached_to"] == "lead"


def test_retired_patient_email_does_not_attach(client, signed_in, clinic, make_patient):
    from datetime import UTC, datetime

    org, _, headers = signed_in
    kept = make_patient(org, "Kept", "One")
    make_patient(org, email=fake_email('gone', 'x.example.test'), retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    r = client.post("/api/leads", json=body(clinic, email=fake_email('gone', 'x.example.test')), headers=headers)
    assert r.get_json()["attached_to"] == "lead"


def test_other_org_patient_email_does_not_attach(client, signed_in, clinic, make_patient, make_org):
    make_patient(make_org("Other"), email=fake_email('testa', 'clinic.example.test'))
    r = client.post("/api/leads", json=body(clinic, email=fake_email('testa', 'clinic.example.test')), headers=signed_in[2])
    assert r.get_json()["attached_to"] == "lead"


def test_lead_requires_phone_or_email(client, signed_in, clinic):
    r = client.post("/api/leads", json=body(clinic, phone=None), headers=signed_in[2])
    assert (r.status_code, r.get_json()["error"]) == (422, "validation_error")
    assert set(r.get_json()["fields"]) == {"phone", "email"}


def test_email_alone_is_enough(client, signed_in, clinic):
    r = client.post("/api/leads", json=body(clinic, phone=None, email=fake_email('a', 'b.example.test')), headers=signed_in[2])
    assert r.status_code == 201


@pytest.mark.parametrize(
    "over,field",
    [
        ({"phone": "abc"}, "phone"),
        ({"email": "nope"}, "email"),
        ({"message": "  "}, "message"),
        ({"source": "website_form"}, "source"),
        ({"full_name": " "}, "full_name"),
    ],
)
def test_invalid_input_is_422(client, signed_in, clinic, over, field):
    r = client.post("/api/leads", json=body(clinic, **over), headers=signed_in[2])
    assert (r.status_code, r.get_json()["fields"]) == (422, [field])


def test_other_org_clinic_is_422(client, signed_in, make_org, make_clinic):
    foreign = make_clinic(make_org("Other"), "Foreign")
    r = client.post("/api/leads", json=body(foreign), headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["clinic_id"]})
    assert client.post("/api/leads", json=body(foreign, clinic_id=str(uuid4())), headers=signed_in[2]).status_code == 422


def test_record_enquiry_without_staff_member(app_session, make_org, make_clinic, owner_engine):
    org = make_org("Public")
    clinic = make_clinic(org, "Web")
    set_tenant_context(app_session, organization_id=org.id, account_id=None)
    result = record_enquiry(
        app_session,
        full_name="Web Visitor",
        phone=None,
        email=fake_email('v', 'x.example.test'),
        clinic_id=clinic.id,
        source="website_form",
        message="Hi",
        preferred_contact_time="evenings",
        staff_member_id=None,
    )
    app_session.commit()
    assert result.attached_to == "lead" and result.patient_id is None
    [enq] = rows(owner_engine, "SELECT created_by_staff_member_id, preferred_contact_time FROM enquiries")
    assert (enq.created_by_staff_member_id, enq.preferred_contact_time) == (None, "evenings")


def test_audit_detail_has_no_pii(client, signed_in, clinic, audit_rows):
    client.post("/api/leads", json=body(clinic, email=fake_email('pii', 'x.example.test')), headers=signed_in[2])
    [e] = audit_rows(entity_type="lead")
    assert "Testa" not in str(e.detail) and fake_email('pii', 'x.example.test') not in str(e.detail)


def test_record_enquiry_without_tenant_context_fails_loudly(app_session, make_org, make_clinic):
    clinic = make_clinic(make_org("Public"), "Web")
    with pytest.raises(RuntimeError, match="tenant context"):
        record_enquiry(
            app_session,
            full_name="Web Visitor",
            phone=None,
            email=fake_email('v', 'x.example.test'),
            clinic_id=clinic.id,
            source="website_form",
            message="Hi",
            preferred_contact_time=None,
            staff_member_id=None,
        )
