from datetime import date
from pathlib import Path

import pytest

from app.people.core.csv_import import TooManyRows, parse_date, parse_patients_csv
from app.people.core.oib import is_valid_oib

DATA = Path(__file__).parent / "testdata"


def test_parses_croatian_excel_export():
    raw = (DATA / "excel_hr.csv").read_bytes()
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    parsed = parse_patients_csv(raw)
    assert parsed.errors == [] and parsed.ignored_columns == []
    assert [r.line for r in parsed.rows] == [2, 3, 4, 5]
    first = parsed.rows[0]
    assert first.errors == []
    assert first.values["first_name"] == "TestŽFirst" and first.values["last_name"] == "TestČLast"
    assert first.values["date_of_birth"] == "2000-01-02"
    assert first.values["phone"] == "+12025550100"
    assert first.values["address"] == "Testna ulica 1, Testni Đgrad"
    assert first.values["clinic"] == "Centar"
    assert is_valid_oib(first.values["oib"])
    assert parsed.rows[1].values["date_of_birth"] == "2020-01-03"
    assert parsed.rows[2].values["date_of_birth"] == "2000-07-01"


def test_parses_utf8_comma_file_with_bom():
    parsed = parse_patients_csv((DATA / "utf8_bom.csv").read_bytes())
    assert parsed.ignored_columns == ["extra"]
    assert [r.values["first_name"] for r in parsed.rows] == ["Testo", "Testp, Testm"]
    assert parsed.rows[0].values["last_name"] == "TestŠLast" and parsed.rows[0].errors == []


def test_row_errors_are_reported_per_line():
    parsed = parse_patients_csv((DATA / "excel_hr.csv").read_bytes())
    bad = parsed.rows[3]
    assert bad.line == 5
    assert bad.errors == ["invalid_date", "invalid_phone", "invalid_email", "invalid_oib"]


def test_missing_names_and_future_dates():
    parsed = parse_patients_csv(b"ime,prezime,datum_rodjenja\n,Testic,2999-01-01\nTesta,,\n")
    assert parsed.rows[0].errors == ["missing_first_name", "invalid_date"]
    assert parsed.rows[1].errors == ["missing_last_name"]


def test_missing_required_columns_and_empty_file():
    assert parse_patients_csv(b"telefon,oib\n1,2\n").errors == ["missing_column_first_name", "missing_column_last_name"]
    assert parse_patients_csv(b" \n\n").errors == ["empty_file"]


def test_too_many_rows_stops_early():
    with pytest.raises(TooManyRows):
        parse_patients_csv(b"ime,prezime\n" + b"A,B\n" * 6, max_rows=5)


def test_parse_date_formats():
    assert parse_date("02.01.2000") == date(2000, 1, 2)
    assert parse_date("2.1.2000.") == date(2000, 1, 2)
    assert parse_date("31.02.2000") is None and parse_date("2000/01/02") is None


def test_nul_bytes_and_replacement_characters_are_unsupported():
    assert parse_patients_csv(b"ime,prezime\nA\x00,B\n").errors == ["unsupported_file"]
    assert parse_patients_csv("ime,prezime\n".encode() + "\ufffd\ufffd,B\n".encode()).errors == ["unsupported_file"]


def test_oversized_cell_is_a_file_error():
    assert parse_patients_csv(b"ime,prezime\n" + b"A" * 200_000 + b",B\n").errors == ["invalid_file"]
