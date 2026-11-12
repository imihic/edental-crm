from testing import fake_email

import pytest
import sqlalchemy.exc
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.people.models import Enquiry, Lead


@pytest.fixture
def org_clinic(make_org, make_clinic):
    org = make_org("A")
    return org, make_clinic(org, "C")


def add(owner_engine, obj):
    with Session(owner_engine) as s:
        s.add(obj)
        s.commit()


def test_lead_defaults_and_generated_search_text(owner_engine, org_clinic):
    org, clinic = org_clinic
    lead = Lead(organization_id=org.id, clinic_id=clinic.id, full_name="Těstić Štestić", email=fake_email('X', 'Ex.example.test'))
    add(owner_engine, lead)
    with owner_engine.connect() as conn:
        row = conn.execute(text("SELECT stage, search_text FROM leads")).one()
    assert row.stage == "new" and "testic stestic" in row.search_text and fake_email('x', 'ex.example.test') in row.search_text


@pytest.mark.parametrize(
    "fields",
    [
        {"stage": "lost"},
        {"stage": "new", "lost_reason": "price"},
        {"stage": "converted"},
        {"stage": "bogus"},
        {"full_name": ""},
    ],
)
def test_lead_checks(owner_engine, org_clinic, fields):
    org, clinic = org_clinic
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        add(owner_engine, Lead(**{"organization_id": org.id, "clinic_id": clinic.id, "full_name": "A B", **fields}))


def test_lead_clinic_must_belong_to_same_org(owner_engine, make_org, make_clinic):
    a, b = make_org("A"), make_org("B")
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        add(owner_engine, Lead(organization_id=a.id, clinic_id=make_clinic(b, "X").id, full_name="A B"))


def test_enquiry_needs_a_lead_or_a_patient(owner_engine, org_clinic):
    org, clinic = org_clinic
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        add(owner_engine, Enquiry(organization_id=org.id, clinic_id=clinic.id, source="phone", message="x"))


def test_enquiry_source_and_length_checks(owner_engine, org_clinic, make_patient):
    org, clinic = org_clinic
    p = make_patient(org)
    for fields in ({"source": "carrier_pigeon"}, {"message": "x" * 2001}, {"preferred_contact_time": "x" * 101}):
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            add(
                owner_engine,
                Enquiry(**{"organization_id": org.id, "clinic_id": clinic.id, "patient_id": p.id, "source": "phone", "message": "m", **fields}),
            )


def test_app_role_privileges(owner_engine):
    with owner_engine.connect() as conn:
        for table in ("leads", "enquiries"):
            privs = {
                p: conn.execute(text("SELECT has_table_privilege('crm_app', :t, :p)"), {"t": f"public.{table}", "p": p}).scalar_one()
                for p in ("SELECT", "INSERT", "UPDATE", "DELETE")
            }
            assert privs == {"SELECT": True, "INSERT": True, "UPDATE": True, "DELETE": False}
