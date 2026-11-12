from datetime import UTC, datetime

import pytest

STAGE_KEYS = {"new", "contacted", "consultation_booked", "converted", "lost"}


@pytest.fixture
def clinic(signed_in, make_clinic):
    return make_clinic(signed_in[0], "Centar")


def names(r):
    return [i["full_name"] for i in r.get_json()["items"]]


def test_lead_search_ignores_diacritics(client, signed_in, clinic, make_lead):
    make_lead(signed_in[0], clinic, "Sample Těstić")
    make_lead(signed_in[0], clinic, "Dummy Example")
    assert names(client.get("/api/leads", query_string={"q": "TESTIC"})) == ["Sample Těstić"]
    assert names(client.get("/api/leads", query_string={"q": "testić"})) == ["Sample Těstić"]


def test_lead_search_by_phone_and_typo_and_wildcards(client, signed_in, clinic, make_lead):
    make_lead(signed_in[0], clinic, "Sample Testić", phone_e164="+12025550100")
    make_lead(signed_in[0], clinic, "Dummy Example")
    assert names(client.get("/api/leads", query_string={"q": "00 1/202-555-0100"})) == ["Sample Testić"]
    assert names(client.get("/api/leads", query_string={"q": "testci"})) == ["Sample Testić"]
    assert names(client.get("/api/leads", query_string={"q": "%"})) == []


def test_counts_per_stage_ignore_stage_filter(client, signed_in, clinic, make_lead):
    org = signed_in[0]
    make_lead(org, clinic, "A One")
    make_lead(org, clinic, "B Two")
    make_lead(org, clinic, "C Three", stage="contacted")
    make_lead(org, clinic, "D Four", stage="lost", lost_reason="price")
    r = client.get("/api/leads", query_string={"stage": "new"})
    body = r.get_json()
    assert body["total"] == 2 and len(body["items"]) == 2
    assert body["counts"] == {"new": 2, "contacted": 1, "consultation_booked": 0, "converted": 0, "lost": 1}
    assert set(body["counts"]) == STAGE_KEYS


def test_counts_respect_q_and_clinic_and_exclude_retired(client, signed_in, clinic, make_lead, make_clinic, make_patient):
    org = signed_in[0]
    other = make_clinic(org, "Other")
    kept = make_patient(org)
    make_lead(org, clinic, "Testa Testić")
    make_lead(org, other, "Testa Testač")
    make_lead(org, clinic, "Testa Gone", retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    make_lead(org, clinic, "Zed Zed")
    body = client.get("/api/leads", query_string={"q": "testa", "clinic_id": str(clinic.id)}).get_json()
    assert body["total"] == 1 and names(client.get("/api/leads", query_string={"q": "testa", "clinic_id": str(clinic.id)})) == ["Testa Testić"]
    assert body["counts"]["new"] == 1


def test_empty_counts_have_all_keys(client, signed_in):
    body = client.get("/api/leads").get_json()
    assert body == {"items": [], "total": 0, "counts": dict.fromkeys(STAGE_KEYS, 0)}


def test_other_org_leads_invisible(client, signed_in, make_org, make_clinic, make_lead):
    org = make_org("Other")
    make_lead(org, make_clinic(org, "X"), "Secret Person")
    assert client.get("/api/leads").get_json()["total"] == 0


def test_pagination_and_bounds(client, signed_in, clinic, make_lead):
    for i in range(3):
        make_lead(signed_in[0], clinic, f"Lead {i}")
    body = client.get("/api/leads", query_string={"page": 2, "page_size": 2}).get_json()
    assert body["total"] == 3 and len(body["items"]) == 1
    assert client.get("/api/leads", query_string={"page": 10001}).status_code == 422
    assert client.get("/api/leads", query_string={"stage": "bogus"}).status_code == 422


def test_requires_login(client):
    assert client.get("/api/leads").status_code == 401
