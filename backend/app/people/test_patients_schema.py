from testing import fake_email

import pytest
import sqlalchemy.exc
from sqlalchemy import select, text

from app.people.models import Patient
from app.platform.db import set_tenant_context


def test_patient_rls_and_defaults(app_session, make_org, make_patient):
    a, b = make_org("A"), make_org("B")
    make_patient(a, first_name="Testa")
    make_patient(b, first_name="Testb")
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    rows = app_session.scalars(select(Patient)).all()
    assert [p.first_name for p in rows] == ["Testa"]
    assert rows[0].preferred_language == "en"
    assert rows[0].retired_at is None and rows[0].created_at is not None


def test_oib_unique_per_org_but_not_across(make_org, make_patient):
    a, b = make_org("A"), make_org("B")
    make_patient(a, oib="11111111119")
    make_patient(b, oib="11111111119")
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        make_patient(a, first_name="Dup", oib="11111111119")


def test_search_text_is_unaccented(owner_engine, make_org, make_patient):
    org = make_org("A")
    p = make_patient(org, first_name="Těstić", last_name="Štestić", email=fake_email('X', 'Ex.example.test'))
    with owner_engine.connect() as conn:
        st = conn.execute(text("SELECT search_text FROM patients WHERE id = :i"), {"i": p.id}).scalar_one()
    assert "testic" in st and "stestic" in st and fake_email('x', 'ex.example.test') in st


def test_app_role_cannot_delete(owner_engine):
    with owner_engine.connect() as conn:
        assert not conn.execute(text("SELECT has_table_privilege('crm_app','public.patients','DELETE')")).scalar_one()
