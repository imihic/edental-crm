from testing import fake_email

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy.exc
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.people.models import Consent

BODY = {"purpose": "marketing", "granted": True, "source": "form"}


def post(client, h, kind, subject_id, **body):
    return client.post(f"/api/{kind}/{subject_id}/consents", json={**BODY, **body}, headers=h)


def get(client, kind, subject_id):
    return client.get(f"/api/{kind}/{subject_id}/consents")


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def add_link(client, h, patient_id) -> str:
    r = client.post(
        f"/api/patients/{patient_id}/guardians",
        json={"relationship": "parent", "contact": {"full_name": "Testg Testić"}},
        headers=h,
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def test_unknown_when_no_entries(client, signed_in, make_patient):
    org, _, _ = signed_in
    p = make_patient(org)
    r = get(client, "patients", p.id)
    assert (r.status_code, r.get_json()) == (200, {"current": {"marketing": "unknown"}, "history": []})
    assert client.get(f"/api/patients/{p.id}").get_json()["consent"] == {"marketing": "unknown"}


def test_consent_history_and_latest_wins(client, signed_in, make_patient, owner_engine):
    org, staff, h = signed_in
    p = make_patient(org)
    t = datetime(2026, 1, 1, tzinfo=UTC)
    with Session(owner_engine) as s:
        s.add(
            Consent(
                organization_id=org.id, patient_id=p.id, purpose="marketing", granted=False, source="paper",
                recorded_at=t + timedelta(days=1),
            )
        )
        s.add(
            Consent(
                organization_id=org.id, patient_id=p.id, purpose="marketing", granted=True, source="form",
                recorded_at=t,
            )
        )
        s.commit()
    out = get(client, "patients", p.id).get_json()
    assert out["current"] == {"marketing": "withdrawn"}
    assert [e["granted"] for e in out["history"]] == [False, True]
    assert client.get(f"/api/patients/{p.id}").get_json()["consent"] == {"marketing": "withdrawn"}
    assert post(client, h, "patients", p.id, granted=True, source="verbal").status_code == 201
    out = get(client, "patients", p.id).get_json()
    assert out["current"] == {"marketing": "granted"}
    assert out["history"][0]["source"] == "verbal"
    assert out["history"][0]["recorded_by_staff_member_id"] == str(staff.id)


def test_withdrawal_is_a_new_row_not_an_update(client, signed_in, make_patient, owner_engine, app_session, audit_rows):
    org, _, h = signed_in
    p = make_patient(org)
    first = post(client, h, "patients", p.id)
    assert first.status_code == 201, first.get_json()
    second = post(client, h, "patients", p.id, granted=False, source="paper")
    assert second.status_code == 201
    with owner_engine.connect() as conn:
        rows = conn.execute(text("SELECT granted FROM consents ORDER BY recorded_at, id")).scalars().all()
    assert rows == [True, False]
    created = {e.entity_id: e.detail for e in audit_rows("create", "consent")}
    assert created == {
        UUID(first.get_json()["id"]): {"subject": "patient", "purpose": "marketing", "granted": True},
        UUID(second.get_json()["id"]): {"subject": "patient", "purpose": "marketing", "granted": False},
    }
    for sql in ("UPDATE consents SET granted = true", "DELETE FROM consents"):
        with pytest.raises(sqlalchemy.exc.ProgrammingError, match="permission denied"):
            app_session.execute(text(sql))
        app_session.rollback()
    with owner_engine.connect() as conn:
        for priv in ("UPDATE", "DELETE"):
            assert not conn.execute(
                text("SELECT has_table_privilege('crm_app', 'public.consents', :p)"), {"p": priv}
            ).scalar_one()


def test_minor_requires_guardian_link(client, signed_in, make_patient):
    org, _, h = signed_in
    minor = make_patient(org, "Mali", "Testić", date_of_birth=date.today().replace(year=date.today().year - 10))
    other = make_patient(org, "Drugi", "Testić")
    expected = {"error": "validation_error", "fields": ["given_by_guardian_link_id"]}
    r = post(client, h, "patients", minor.id)
    assert (r.status_code, r.get_json()) == (422, expected)
    foreign_link = add_link(client, h, other.id)
    r = post(client, h, "patients", minor.id, given_by_guardian_link_id=foreign_link)
    assert (r.status_code, r.get_json()) == (422, expected)
    r = post(client, h, "patients", minor.id, given_by_guardian_link_id=str(uuid4()))
    assert (r.status_code, r.get_json()) == (422, expected)
    link = add_link(client, h, minor.id)
    r = post(client, h, "patients", minor.id, given_by_guardian_link_id=link)
    assert r.status_code == 201 and r.get_json()["given_by_guardian_link_id"] == link
    assert get(client, "patients", minor.id).get_json()["current"] == {"marketing": "granted"}


def test_ending_and_readding_guardian_preserves_minor_consent(client, signed_in, make_patient, owner_engine):
    org, _, h = signed_in
    minor = make_patient(org, "Mali", "Testić", date_of_birth=date.today() - timedelta(days=3650))
    guardian = make_patient(org, "Testg", "Testić")
    links_url = f"/api/patients/{minor.id}/guardians"
    guardian_body = {"relationship": "parent", "guardian_patient_id": str(guardian.id)}
    first = client.post(links_url, json=guardian_body, headers=h)
    assert first.status_code == 201, first.get_json()
    first_id = first.get_json()["id"]
    grant = post(client, h, "patients", minor.id, given_by_guardian_link_id=first_id)
    assert grant.status_code == 201, grant.get_json()

    assert client.delete(f"{links_url}/{first_id}", json={}, headers=h).status_code == 204
    assert client.get(f"/api/patients/{minor.id}").get_json()["guardians"] == []
    assert client.get(f"/api/patients/{guardian.id}").get_json()["guardian_of"] == []
    assert get(client, "patients", minor.id).get_json() == {
        "current": {"marketing": "granted"}, "history": [grant.get_json()]
    }
    rejected = post(client, h, "patients", minor.id, granted=False, given_by_guardian_link_id=first_id)
    assert (rejected.status_code, rejected.get_json()) == (
        422, {"error": "validation_error", "fields": ["given_by_guardian_link_id"]}
    )

    replacement = client.post(links_url, json=guardian_body, headers=h)
    assert replacement.status_code == 201, replacement.get_json()
    replacement_id = replacement.get_json()["id"]
    assert replacement_id != first_id
    assert client.get(f"/api/patients/{minor.id}").get_json()["guardians"] == [replacement.get_json()]
    withdrawal = post(client, h, "patients", minor.id, granted=False, given_by_guardian_link_id=replacement_id)
    assert withdrawal.status_code == 201, withdrawal.get_json()
    assert get(client, "patients", minor.id).get_json() == {
        "current": {"marketing": "withdrawn"}, "history": [withdrawal.get_json(), grant.get_json()]
    }
    with owner_engine.connect() as conn:
        created, ended = conn.execute(
            text("SELECT created_at, ended_at FROM guardian_links WHERE id = :id"), {"id": first_id}
        ).one()
    assert created <= datetime.fromisoformat(grant.get_json()["recorded_at"]) <= ended
    assert ended <= datetime.fromisoformat(withdrawal.get_json()["recorded_at"])


def test_adult_guardian_link_is_optional_but_must_belong(client, signed_in, make_patient):
    org, _, h = signed_in
    adult = make_patient(org, "Testa", "Testić", date_of_birth=date(1980, 1, 1))
    nodob = make_patient(org, "Bez", "Datuma")
    other = make_patient(org, "Drugi", "Testić")
    assert post(client, h, "patients", adult.id).status_code == 201
    assert post(client, h, "patients", nodob.id).status_code == 201
    r = post(client, h, "patients", adult.id, given_by_guardian_link_id=add_link(client, h, other.id))
    assert (r.status_code, r.get_json()["fields"]) == (422, ["given_by_guardian_link_id"])
    own = add_link(client, h, adult.id)
    assert post(client, h, "patients", adult.id, given_by_guardian_link_id=own).status_code == 201


def test_lead_consent_ignores_guardian_rules(client, signed_in, clinic, make_lead, audit_rows):
    org, _, h = signed_in
    lead = make_lead(org, clinic)
    r = post(client, h, "leads", lead.id, source="verbal", granted=False)
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["given_by_guardian_link_id"] is None
    out = get(client, "leads", lead.id).get_json()
    assert out["current"] == {"marketing": "withdrawn"} and len(out["history"]) == 1
    assert client.get(f"/api/leads/{lead.id}").get_json()["consent"] == {"marketing": "withdrawn"}
    (entry,) = audit_rows("create", "consent")
    assert entry.entity_id == UUID(r.get_json()["id"])
    assert entry.detail == {"subject": "lead", "purpose": "marketing", "granted": False}
    r = post(client, h, "leads", lead.id, given_by_guardian_link_id=str(uuid4()))
    assert r.status_code == 201 and r.get_json()["given_by_guardian_link_id"] is None


def test_invalid_body(client, signed_in, make_patient):
    org, _, h = signed_in
    p = make_patient(org)
    for bad in ({"source": "enquiry_form"}, {"source": "merge"}, {"purpose": "sms"}, {"granted": "maybe"}):
        assert post(client, h, "patients", p.id, **bad).status_code == 422, bad


def test_retired_unknown_and_other_org_subjects(client, signed_in, make_org, make_patient, make_clinic, make_lead, owner_engine):
    org, _, h = signed_in
    keep, gone = make_patient(org, "Keep", "A"), make_patient(org, "Gone", "A")
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE patients SET retired_at = now(), retired_into_patient_id = :k WHERE id = :g"),
            {"k": keep.id, "g": gone.id},
        )
    r = post(client, h, "patients", gone.id)
    assert (r.status_code, r.get_json()) == (410, {"error": "merged", "merged_into": str(keep.id)})
    assert get(client, "patients", gone.id).status_code == 410
    lead = make_lead(org, make_clinic(org, "C"))
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE leads SET retired_at = now(), retired_into_patient_id = :k WHERE id = :l"),
            {"k": keep.id, "l": lead.id},
        )
    assert post(client, h, "leads", lead.id).status_code == 410
    assert get(client, "leads", lead.id).status_code == 410
    foreign_org = make_org("Other")
    foreign = make_patient(foreign_org, "For", "Eign")
    foreign_lead = make_lead(foreign_org, make_clinic(foreign_org, "X"))
    for kind, sid in (("patients", foreign.id), ("patients", uuid4()), ("leads", foreign_lead.id), ("leads", uuid4())):
        assert get(client, kind, sid).status_code == 404
        assert post(client, h, kind, sid).status_code == 404


def test_requires_login(client):
    assert client.get(f"/api/patients/{uuid4()}/consents").status_code == 401
    assert client.post(f"/api/leads/{uuid4()}/consents", json=BODY).status_code in (401, 403)


def test_consent_requires_exactly_one_subject(owner_engine, make_org, make_patient, make_clinic, make_lead):
    org = make_org("A")
    p = make_patient(org)
    lead = make_lead(org, make_clinic(org, "C"))
    for fields in ({}, {"patient_id": p.id, "lead_id": lead.id}):
        with pytest.raises(sqlalchemy.exc.IntegrityError), Session(owner_engine) as s:
            s.add(Consent(organization_id=org.id, purpose="marketing", granted=True, source="form", **fields))
            s.commit()


def test_guardian_link_must_exist_in_same_org(owner_engine, make_org, make_patient):
    org = make_org("A")
    p = make_patient(org)
    with pytest.raises(sqlalchemy.exc.IntegrityError), Session(owner_engine) as s:
        s.add(
            Consent(
                organization_id=org.id, patient_id=p.id, purpose="marketing", granted=True, source="form",
                given_by_guardian_link_id=uuid4(),
            )
        )
        s.commit()


def test_consent_on_a_converted_lead_points_at_the_patient(client, signed_in, clinic, make_lead, owner_engine):
    org, _, h = signed_in
    lead = make_lead(org, clinic)
    converted = client.post(f"/api/leads/{lead.id}/convert", json={"first_name": "Testan", "last_name": "Testač"}, headers=h)
    patient_id = converted.get_json()["id"]
    r = post(client, h, "leads", lead.id)
    assert (r.status_code, r.get_json()) == (409, {"error": "lead_converted", "patient_id": patient_id})
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM consents WHERE lead_id = :l"), {"l": lead.id}).scalar_one() == 0
    assert post(client, h, "patients", patient_id).status_code == 201


def test_consent_waits_for_a_merge_holding_the_patient_lock(
    app, signed_in, make_patient, owner_engine, login, csrf
):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    org, _, _ = signed_in
    kept, retired = make_patient(org, "Kept", "One"), make_patient(org, "Gone", "Two")
    c = app.test_client()
    login(c, fake_email('testa', 'clinic.example.test'))
    headers = csrf(c)
    with owner_engine.connect() as conn, ThreadPoolExecutor(1) as pool:
        conn.execute(text("SELECT 1 FROM patients WHERE id = :i FOR UPDATE"), {"i": retired.id})
        pending = pool.submit(lambda: post(c, headers, "patients", retired.id))
        sleep(0.5)
        assert not pending.done()
        conn.execute(
            text("UPDATE patients SET retired_at = now(), retired_into_patient_id = :k WHERE id = :i"),
            {"k": kept.id, "i": retired.id},
        )
        conn.commit()
        r = pending.result(timeout=10)
    assert (r.status_code, r.get_json()) == (410, {"error": "merged", "merged_into": str(kept.id)})
    with owner_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM consents")).scalar_one() == 0
