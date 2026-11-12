from datetime import UTC, datetime

import pytest

OIB = "11111111119"


def names(r):
    return [f'{p["first_name"]} {p["last_name"]}' for p in r.get_json()["items"]]


@pytest.mark.parametrize("q", ["testic", "TĚSTIĆ", "Testić"])
def test_search_ignores_diacritics(q, client, signed_in, make_patient):
    make_patient(signed_in[0], "Sample", "Těstić")
    make_patient(signed_in[0], "Dummy", "Example")
    assert names(client.get("/api/patients", query_string={"q": q})) == ["Sample Těstić"]


@pytest.mark.parametrize("q", ["+1 202 555 0100", "0012025550100", "00 1/202-555-0100"])
def test_search_by_phone_formats(q, client, signed_in, make_patient):
    make_patient(signed_in[0], "Sample", "Těstić", phone_e164="+12025550100")
    make_patient(signed_in[0], "Dummy", "Example", phone_e164="+447700900000")
    assert names(client.get("/api/patients", query_string={"q": q})) == ["Sample Těstić"]


def test_search_tolerates_a_typo(client, signed_in, make_patient):
    make_patient(signed_in[0], "Sample", "Testić")
    make_patient(signed_in[0], "Dummy", "Example")
    assert names(client.get("/api/patients", query_string={"q": "testci"})) == ["Sample Testić"]


def test_search_escapes_like_wildcards(client, signed_in, make_patient):
    make_patient(signed_in[0], "Testa", "Testić")
    assert names(client.get("/api/patients", query_string={"q": "%"})) == []


def test_list_is_paginated_and_never_contains_raw_oib(client, signed_in, make_patient):
    make_patient(signed_in[0], "Cc", "Zed", oib=OIB)
    make_patient(signed_in[0], "Aa", "Alpha")
    make_patient(signed_in[0], "Bb", "Beta")
    r = client.get("/api/patients", query_string={"page": 2, "page_size": 2})
    body = r.get_json()
    assert body["total"] == 3 and names(r) == ["Cc Zed"]
    assert body["items"][0]["oib_masked"] == "*******1119"
    assert OIB not in r.get_data(as_text=True)
    assert set(body["items"][0]) == {
        "id", "first_name", "last_name", "date_of_birth", "phone", "email", "oib_masked"
    }


def test_list_excludes_retired_and_other_orgs(client, signed_in, make_patient, make_org):
    kept = make_patient(signed_in[0], "Kept", "One")
    make_patient(signed_in[0], "Gone", "Two", retired_at=datetime.now(UTC), retired_into_patient_id=kept.id)
    make_patient(make_org("Other"), "Else", "Where")
    assert names(client.get("/api/patients")) == ["Kept One"]


def test_page_size_is_capped(client, signed_in):
    assert client.get("/api/patients", query_string={"page_size": 101}).status_code == 422


def test_huge_page_is_a_validation_error_not_500(client, signed_in):
    r = client.get("/api/patients", query_string={"page": 10**30})
    assert (r.status_code, r.get_json()["error"]) == (422, "validation_error")


@pytest.mark.parametrize("q", ["1111", "11111111119", "1111111"])
def test_search_never_matches_oib_fragments(q, client, signed_in, make_patient):
    make_patient(signed_in[0], "Testa", "Testić", oib=OIB)
    assert names(client.get("/api/patients", query_string={"q": q})) == []


def test_oib_is_not_in_search_text(signed_in, make_patient, owner_engine):
    from sqlalchemy import text

    make_patient(signed_in[0], "Testa", "Testić", oib=OIB)
    with owner_engine.connect() as conn:
        assert OIB not in conn.execute(text("SELECT search_text FROM patients")).scalar_one()
