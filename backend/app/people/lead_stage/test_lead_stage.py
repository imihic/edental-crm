from testing import fake_email

from datetime import UTC, datetime

import pytest


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def move(client, headers, lead, **body):
    return client.post(f"/api/leads/{lead.id}/stage", json=body, headers=headers)


def test_valid_move_is_audited_without_pii(client, signed_in, clinic, make_lead, audit_rows):
    org, staff, headers = signed_in
    lead = make_lead(org, clinic)
    r = move(client, headers, lead, stage="contacted")
    assert r.status_code == 200 and r.get_json()["stage"] == "contacted"
    [e] = audit_rows(action="update", entity_type="lead")
    assert (e.entity_id, e.staff_member_id, e.detail) == (lead.id, staff.id, {"fields": ["stage"]})


def test_lost_requires_reason(client, signed_in, clinic, make_lead):
    lead = make_lead(signed_in[0], clinic)
    r = move(client, signed_in[2], lead, stage="lost")
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["lost_reason"]})
    assert move(client, signed_in[2], lead, stage="lost", lost_reason="bogus").status_code == 422


def test_lost_then_reopen_clears_reason(client, signed_in, clinic, make_lead):
    lead = make_lead(signed_in[0], clinic)
    out = move(client, signed_in[2], lead, stage="lost", lost_reason="price", lost_note="  too dear ").get_json()
    assert (out["stage"], out["lost_reason"], out["lost_note"]) == ("lost", "price", "too dear")
    out = move(client, signed_in[2], lead, stage="new").get_json()
    assert (out["stage"], out["lost_reason"], out["lost_note"]) == ("new", None, None)


def test_cannot_set_converted_via_stage(client, signed_in, clinic, make_lead):
    lead = make_lead(signed_in[0], clinic)
    r = move(client, signed_in[2], lead, stage="converted")
    assert (r.status_code, r.get_json()) == (409, {"error": "invalid_transition"})


@pytest.mark.parametrize("stage,target", [("new", "new"), ("contacted", "new"), ("lost", "contacted")])
def test_invalid_moves_are_409(client, signed_in, clinic, make_lead, stage, target):
    kwargs = {"lost_reason": "price"} if stage == "lost" else {}
    lead = make_lead(signed_in[0], clinic, stage=stage, **kwargs)
    assert move(client, signed_in[2], lead, stage=target).status_code == 409


def test_converted_lead_is_frozen(client, signed_in, clinic, make_lead, make_patient):
    p = make_patient(signed_in[0])
    lead = make_lead(signed_in[0], clinic, stage="converted", converted_patient_id=p.id)
    assert move(client, signed_in[2], lead, stage="new").status_code == 409


def test_other_org_404_retired_410_and_csrf(client, signed_in, clinic, make_lead, make_org, make_clinic, make_patient):
    other = make_org("Other")
    foreign = make_lead(other, make_clinic(other, "X"))
    assert move(client, signed_in[2], foreign, stage="contacted").status_code == 404
    kept = make_patient(signed_in[0])
    gone = make_lead(signed_in[0], clinic, retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    assert move(client, signed_in[2], gone, stage="contacted").status_code == 410
    own = make_lead(signed_in[0], clinic)
    assert client.post(f"/api/leads/{own.id}/stage", json={"stage": "contacted"}).status_code in (400, 403)


def _fresh_client(app, login, csrf):
    c = app.test_client()
    login(c, fake_email('testa', 'clinic.example.test'))
    return c, csrf(c)


def test_stage_change_waits_for_a_conversion_holding_the_lead_lock(
    app, client, signed_in, clinic, make_lead, make_patient, owner_engine, login, csrf
):
    from concurrent.futures import ThreadPoolExecutor
    from time import sleep

    from sqlalchemy import text

    org, _, _ = signed_in
    lead = make_lead(org, clinic)
    patient = make_patient(org, "Testan", "Testač")
    c, headers = _fresh_client(app, login, csrf)
    with owner_engine.connect() as conn, ThreadPoolExecutor(1) as pool:
        conn.execute(text("SELECT 1 FROM leads WHERE id = :i FOR UPDATE"), {"i": lead.id})
        pending = pool.submit(lambda: move(c, headers, lead, stage="contacted"))
        sleep(0.5)
        assert not pending.done()
        conn.execute(
            text("UPDATE leads SET stage = 'converted', converted_patient_id = :p WHERE id = :i"),
            {"p": patient.id, "i": lead.id},
        )
        conn.commit()
        r = pending.result(timeout=10)
    assert (r.status_code, r.get_json()) == (409, {"error": "invalid_transition"})
    with owner_engine.connect() as conn:
        row = conn.execute(text("SELECT stage, converted_patient_id FROM leads WHERE id = :i"), {"i": lead.id}).one()
    assert (row.stage, row.converted_patient_id) == ("converted", patient.id)


def test_racing_stage_changes_and_conversions_never_corrupt_a_lead(
    app, signed_in, clinic, make_lead, owner_engine, login, csrf
):
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import text

    org, _, _ = signed_in
    clients = [_fresh_client(app, login, csrf) for _ in range(3)]
    convert_body = {"first_name": "Testan", "last_name": "Testač"}
    with ThreadPoolExecutor(3) as pool:
        for n in range(5):
            lead = make_lead(org, clinic, f"Lead {n}")
            jobs = [
                pool.submit(lambda c=c, h=h: c.post(f"/api/leads/{lead.id}/convert", json=convert_body, headers=h))
                for c, h in clients[:2]
            ] + [pool.submit(lambda: move(*clients[2], lead, stage="contacted"))]
            converts = sorted(j.result(timeout=20).status_code for j in jobs[:2])
            stage = jobs[2].result(timeout=20).status_code
            assert converts == [201, 409]
            assert stage in (200, 409)
            with owner_engine.connect() as conn:
                row = conn.execute(
                    text("SELECT stage, converted_patient_id FROM leads WHERE id = :i"), {"i": lead.id}
                ).one()
            assert row.stage == "converted" and row.converted_patient_id is not None
