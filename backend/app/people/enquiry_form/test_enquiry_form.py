from uuid import uuid4

import pytest
from sqlalchemy import text


def forms(owner_engine):
    with owner_engine.connect() as conn:
        return conn.execute(text("SELECT id, clinic_id, key, enabled, rotated_at FROM enquiry_forms")).all()


@pytest.fixture
def clinic(manager_in, owner_engine):
    with owner_engine.connect() as conn:
        return conn.execute(text("SELECT id FROM clinics WHERE name = 'Centar'")).scalar_one()


def test_manager_gets_and_regenerates_key(client, manager_in, clinic, owner_engine, audit_rows):
    org, staff, headers = manager_in
    r = client.get(f"/api/clinics/{clinic}/enquiry-form")
    out = r.get_json()
    assert r.status_code == 200 and out["enabled"] is True
    assert len(out["key"]) == 32 and out["path"] == f"/enquiry/{out['key']}"
    assert client.get(f"/api/clinics/{clinic}/enquiry-form").get_json() == out
    assert len(forms(owner_engine)) == 1 and forms(owner_engine)[0].rotated_at is None

    r2 = client.post(f"/api/clinics/{clinic}/enquiry-form/regenerate", json={}, headers=headers)
    new = r2.get_json()
    assert r2.status_code == 200 and new["key"] != out["key"] and new["path"] == f"/enquiry/{new['key']}"
    [form] = forms(owner_engine)
    assert form.key == new["key"] and form.rotated_at is not None
    [e] = audit_rows(entity_type="enquiry_form")
    assert (e.action, e.staff_member_id, e.detail) == ("update", staff.id, {"fields": ["key"]})


def test_regenerate_creates_form_when_none_yet(client, manager_in, clinic, owner_engine):
    r = client.post(f"/api/clinics/{clinic}/enquiry-form/regenerate", json={}, headers=manager_in[2])
    assert r.status_code == 200 and len(forms(owner_engine)) == 1


def test_only_clinic_manager(client, signed_in, make_clinic):
    clinic = make_clinic(signed_in[0], "Centar")
    assert client.get(f"/api/clinics/{clinic.id}/enquiry-form").get_json() == {"error": "forbidden"}
    r = client.post(f"/api/clinics/{clinic.id}/enquiry-form/regenerate", json={}, headers=signed_in[2])
    assert (r.status_code, r.get_json()) == (403, {"error": "forbidden"})


def test_anonymous_is_401(client):
    assert client.get(f"/api/clinics/{uuid4()}/enquiry-form").status_code == 401


def test_other_org_or_unknown_clinic_is_404(client, manager_in, make_org, make_clinic, owner_engine):
    foreign = make_clinic(make_org("Other"), "Foreign")
    for cid in (foreign.id, uuid4()):
        assert client.get(f"/api/clinics/{cid}/enquiry-form").status_code == 404
        r = client.post(f"/api/clinics/{cid}/enquiry-form/regenerate", json={}, headers=manager_in[2])
        assert (r.status_code, r.get_json()) == (404, {"error": "not_found"})
    assert forms(owner_engine) == []
