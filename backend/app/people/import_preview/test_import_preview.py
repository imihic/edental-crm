from testing import fake_email

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

OIB_A = "11111111119"
OIB_B = "22222222226"


def csv_of(*lines: str) -> str:
    return "ime;prezime;datum rođenja;e-mail;oib;klinika\n" + "\n".join(lines) + "\n"


def test_preview_flags_db_and_in_file_duplicates(manager_in, upload, make_patient, audit_rows):
    org, _staff, headers = manager_in
    make_patient(org, "Testa", "Testić", date_of_birth=date(2000, 7, 1), email=fake_email('testa', 'example.test'))
    make_patient(org, "Luka", "Testarić", oib=OIB_A)
    r = upload(
        headers,
        csv_of(
            "Testa;Testić;01.07.2000;;;Centar",
            "Testiva;Testnovak;;;;Centar",
            f"Testiva;Testnovak;;{fake_email('testiva', 'example.test')};;Zapad",
            f"Testana;Testnovak;;{fake_email('TESTIVA', 'example.test')};;Zapad",
            f"Pero;Perić;;;{OIB_A};Centar",
            "Testmr;Testaric;;;12345;Centar",
            "Tina;Tomić;;;;Nepoznata",
            f"Žtesta;Testzorić;;;{OIB_B};Centar",
            f"Testz;Testzoric;;;{OIB_B};Centar",
        ),
    )
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    rows = {row["line"]: row for row in body["rows"]}
    assert rows[2]["status"] == "duplicate"
    assert rows[2]["duplicates"][0]["reasons"] == ["name_and_birth_date"]
    assert rows[3]["status"] == "valid" and rows[3]["duplicates"] == [] and rows[3]["in_file_duplicate_of_line"] is None
    assert rows[4]["status"] == "valid"
    assert (rows[5]["status"], rows[5]["in_file_duplicate_of_line"]) == ("duplicate", 4)
    assert rows[6]["status"] == "duplicate" and "oib" in rows[6]["duplicates"][0]["reasons"]
    assert (rows[7]["status"], rows[7]["errors"]) == ("invalid", ["invalid_oib"])
    assert (rows[8]["status"], rows[8]["errors"]) == ("invalid", ["unknown_clinic"])
    assert rows[9]["status"] == "valid"
    assert (rows[10]["status"], rows[10]["in_file_duplicate_of_line"]) == ("duplicate", 9)
    assert body["counts"] == {"total": 9, "valid": 3, "invalid": 2, "duplicate": 4}
    assert body["ignored_columns"] == []
    assert body["import_id"]
    assert audit_rows(entity_type="patient_import") == []


def test_invalid_row_stays_invalid_even_when_it_is_a_duplicate(manager_in, upload, make_patient):
    org, _staff, headers = manager_in
    make_patient(org, "Testa", "Testić", date_of_birth=date(2000, 7, 1))
    r = upload(headers, csv_of("Testa;Testić;01.07.2000;;;Nigdje"))
    assert r.get_json()["rows"][0]["status"] == "invalid"


def test_preview_reads_cp1250_excel_export(manager_in, upload):
    raw = (Path(__file__).parents[1] / "core" / "testdata" / "excel_hr.csv").read_bytes()
    r = upload(manager_in[2], raw)
    assert r.status_code == 200
    assert [row["status"] for row in r.get_json()["rows"]] == ["valid", "valid", "valid", "invalid"]


def test_receptionist_cannot_import(signed_in, upload):
    assert upload(signed_in[2], csv_of("A;B;;;;")).status_code == 403


def test_file_too_large_413(manager_in, upload):
    r = upload(manager_in[2], b"ime;prezime\n" + b"x" * (5 * 1024 * 1024))
    assert (r.status_code, r.get_json()) == (413, {"error": "file_too_large"})


def test_too_many_rows_422(manager_in, upload):
    r = upload(manager_in[2], "ime;prezime\n" + "Testa;Testić\n" * 5001)
    assert (r.status_code, r.get_json()) == (422, {"error": "too_many_rows"})


def test_exactly_5000_rows_is_accepted(manager_in, upload):
    assert upload(manager_in[2], "ime;prezime\n" + "Testa;Testić\n" * 5000).status_code == 200


def test_invalid_base64_422(manager_in, client):
    r = client.post(
        "/api/imports/patients/preview",
        json={"filename": "a.csv", "content_base64": "***not base64***"},
        headers=manager_in[2],
    )
    assert (r.status_code, r.get_json()) == (422, {"error": "validation_error", "fields": ["content_base64"]})


@pytest.mark.parametrize("content", ["", "telefon;oib\n1;2\n"])
def test_unusable_file_422(manager_in, upload, content):
    r = upload(manager_in[2], content)
    assert r.status_code == 422 and r.get_json()["error"] == "invalid_file"


def test_preview_requires_login(upload):
    assert upload({}, "ime;prezime\nA;B\n").status_code == 401


def test_preview_stores_rows_under_the_organization(manager_in, upload, owner_engine):
    org, _staff, headers = manager_in
    import_id = upload(headers, csv_of("Testa;Testić;;;;Centar")).get_json()["import_id"]
    with owner_engine.connect() as conn:
        row = conn.execute(
            text("SELECT organization_id, status, filename FROM patient_imports WHERE id = :i"), {"i": import_id}
        ).one()
    assert tuple(row) == (org.id, "previewed", "patients.csv")


def test_oversized_cell_is_an_invalid_file_not_a_500(manager_in, upload):
    r = upload(manager_in[2], "ime;prezime\n" + "A" * 200_000 + ";B\n")
    assert r.status_code == 422 and r.get_json()["error"] == "invalid_file"


def test_body_over_8_mb_is_413(manager_in, client):
    r = client.post(
        "/api/imports/patients/preview",
        json={"filename": "a.csv", "content_base64": "A" * (9 * 1024 * 1024)},
        headers=manager_in[2],
    )
    assert (r.status_code, r.get_json()) == (413, {"error": "file_too_large"})


@pytest.mark.parametrize("raw", [b"ime;prezime\n\x00\x01\x02Ana;B\n", b"ime;prezime\n" + b"\x81\x88\x90" * 50])
def test_binary_or_mojibake_content_is_unsupported(manager_in, upload, raw):
    r = upload(manager_in[2], raw)
    assert (r.status_code, r.get_json()) == (422, {"error": "unsupported_file"})
