from testing import fake_email

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pyotp
from sqlalchemy import text

from app.identity import Role

OIB_A = "11111111119"
OIB_B = "22222222226"


def csv_of(*lines: str) -> str:
    return "ime;prezime;datum rođenja;e-mail;oib;klinika\n" + "\n".join(lines) + "\n"


def commit(client, headers, import_id, include_duplicates=False):
    return client.post(
        f"/api/imports/patients/{import_id}/commit", json={"include_duplicates": include_duplicates}, headers=headers
    )


def scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


def test_commit_skips_duplicates_by_default_and_sets_no_consent(
    client, manager_in, upload, make_patient, owner_engine, audit_rows
):
    org, staff, headers = manager_in
    make_patient(org, "Testa", "Testić", date_of_birth=date(2000, 7, 1))
    preview = upload(
        headers,
        csv_of(
            "Testa;Testić;01.07.2000;;;Centar",
            "Testiva;Testnovak;;;;Zapad",
            f"Žtesta;Testzorić;;;{OIB_B};Centar",
            "Tina;Tomić;;;;Nigdje",
        ),
    ).get_json()
    r = commit(client, headers, preview["import_id"])
    assert (r.status_code, r.get_json()) == (200, {"created": 2, "skipped": 2})
    with owner_engine.connect() as conn:
        created = conn.execute(
            text(
                "SELECT first_name, preferred_clinic_id IS NOT NULL, oib, import_id FROM patients "
                "WHERE import_id IS NOT NULL ORDER BY first_name"
            )
        ).all()
    assert [(c[0], c[1], c[2]) for c in created] == [("Testiva", True, None), ("Žtesta", True, OIB_B)]
    assert {str(c[3]) for c in created} == {preview["import_id"]}
    assert scalar(owner_engine, "SELECT count(*) FROM consents") == 0
    audits = audit_rows(entity_type="patient_import")
    assert [(a.action, str(a.entity_id), a.detail, a.staff_member_id) for a in audits] == [
        ("create", preview["import_id"], {"created": 2, "skipped": 2}, staff.id)
    ]
    assert audit_rows() == []
    assert scalar(owner_engine, "SELECT status FROM patient_imports") == "committed"


def test_include_duplicates_creates_them_except_oib_clashes(client, manager_in, upload, make_patient, owner_engine):
    org, _staff, headers = manager_in
    make_patient(org, "Testa", "Testić", date_of_birth=date(2000, 7, 1))
    make_patient(org, "Luka", "Testarić", oib=OIB_A)
    preview = upload(
        headers,
        csv_of(
            "Testa;Testić;01.07.2000;;;Centar",
            f"Pero;Perić;;;{OIB_A};Centar",
            f"Žtesta;Testzorić;;;{OIB_B};Centar",
            f"Testz;Testzoric;;;{OIB_B};Centar",
        ),
    ).get_json()
    r = commit(client, headers, preview["import_id"], include_duplicates=True)
    assert (r.status_code, r.get_json()) == (200, {"created": 2, "skipped": 2})
    assert scalar(owner_engine, "SELECT count(*) FROM patients WHERE import_id IS NOT NULL") == 2


def test_commit_skips_rows_whose_oib_was_taken_after_the_preview(client, manager_in, upload, make_patient):
    org, _staff, headers = manager_in
    preview = upload(headers, csv_of(f"Žtesta;Testzorić;;;{OIB_B};Centar", "Testiva;Testnovak;;;;Centar")).get_json()
    make_patient(org, "Netko", "Treći", oib=OIB_B)
    r = commit(client, headers, preview["import_id"])
    assert (r.status_code, r.get_json()) == (200, {"created": 1, "skipped": 1})


def test_commit_twice_409_and_expired_410(client, manager_in, upload, owner_engine):
    _org, _staff, headers = manager_in
    first = upload(headers, csv_of("Testiva;Testnovak;;;;Centar")).get_json()["import_id"]
    assert commit(client, headers, first).status_code == 200
    again = commit(client, headers, first)
    assert (again.status_code, again.get_json()) == (409, {"error": "already_committed"})
    assert scalar(owner_engine, "SELECT count(*) FROM patients") == 1

    old = upload(headers, csv_of("Teste;Testnovak;;;;Centar")).get_json()["import_id"]
    with owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE patient_imports SET created_at = :t WHERE id = :i"),
            {"t": datetime.now(UTC) - timedelta(hours=25), "i": old},
        )
    expired = commit(client, headers, old)
    assert (expired.status_code, expired.get_json()) == (410, {"error": "import_expired"})
    assert scalar(owner_engine, "SELECT count(*) FROM patients") == 1
    assert scalar(owner_engine, "SELECT status FROM patient_imports WHERE id = :i", i=old) == "expired"


def test_receptionist_cannot_commit(client, signed_in):
    assert commit(client, signed_in[2], uuid4()).status_code == 403


def test_unknown_import_404(client, manager_in):
    assert commit(client, manager_in[2], uuid4()).status_code == 404


def test_another_organizations_import_is_invisible(client, manager_in, upload, login, csrf, make_org, make_account, make_staff):
    import_id = upload(manager_in[2], csv_of("Testiva;Testnovak;;;;Centar")).get_json()["import_id"]
    client.post("/api/auth/logout", headers=manager_in[2])
    secret = pyotp.random_base32()
    make_staff(make_org("Other"), make_account(fake_email('o', 'other.example.test'), totp_secret=secret), roles=(Role.CLINIC_MANAGER,))
    login(client, fake_email('o', 'other.example.test'), totp_secret=secret)
    assert commit(client, csrf(client), import_id).status_code == 404


def stored_rows(engine, import_id):
    return scalar(engine, "SELECT rows::text FROM patient_imports WHERE id = :i", i=import_id)


def test_commit_keeps_no_personal_data_in_the_stored_rows(client, manager_in, upload, make_patient, owner_engine):
    org, _staff, headers = manager_in
    make_patient(org, "Testa", "Testić", date_of_birth=date(2000, 7, 1))
    preview = upload(
        headers,
        csv_of("Testa;Testić;01.07.2000;;;Centar", f"Žtesta;Testzorić;;{fake_email('ž', 'example.test')};{OIB_B};Centar"),
    ).get_json()
    assert OIB_B in stored_rows(owner_engine, preview["import_id"])
    assert commit(client, headers, preview["import_id"]).status_code == 200
    stored = stored_rows(owner_engine, preview["import_id"])
    for secret in ("Testa", "Testić", "Žtesta", "Testzori", OIB_B, "example.test", "values", "duplicates"):
        assert secret not in stored
    assert '"status": "duplicate"' in stored and '"line": 3' in stored


def test_expired_preview_is_blanked_on_410_and_on_listing(client, manager_in, upload, owner_engine):
    _org, _staff, headers = manager_in
    first = upload(headers, csv_of(f"Testiva;Testnovak;;;{OIB_B};Centar")).get_json()["import_id"]
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE patient_imports SET created_at = now() - interval '25 hours'"))
    assert commit(client, headers, first).status_code == 410
    assert "Testnovak" not in stored_rows(owner_engine, first)
    second = upload(headers, csv_of(f"Teste;Testnovak;;;{OIB_B};Centar")).get_json()["import_id"]
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE patient_imports SET created_at = now() - interval '25 hours' WHERE id = :i"), {"i": second})
    assert "Testnovak" in stored_rows(owner_engine, second)
    assert client.get("/api/imports").status_code == 200
    assert "Testnovak" not in stored_rows(owner_engine, second)
    assert scalar(owner_engine, "SELECT count(*) FROM patient_imports WHERE status = 'expired'") == 2


def test_committing_one_import_blanks_other_expired_previews(client, manager_in, upload, owner_engine):
    _org, _staff, headers = manager_in
    stale = upload(headers, csv_of(f"Testiva;Testnovak;;;{OIB_B};Centar")).get_json()["import_id"]
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE patient_imports SET created_at = now() - interval '25 hours'"))
    fresh = upload(headers, csv_of(f"Teste;Testić;;;{OIB_A};Centar")).get_json()["import_id"]
    with owner_engine.begin() as conn:
        conn.execute(text("UPDATE patient_imports SET status = 'previewed', rows = (SELECT rows FROM patient_imports WHERE id = :f) WHERE id = :s"), {"f": fresh, "s": stale})
        conn.execute(text("UPDATE patient_imports SET created_at = now() - interval '25 hours' WHERE id = :s"), {"s": stale})
    assert "Testić" in stored_rows(owner_engine, stale)
    assert commit(client, headers, fresh).status_code == 200
    assert "Testić" not in stored_rows(owner_engine, stale)
    assert scalar(owner_engine, "SELECT status FROM patient_imports WHERE id = :i", i=stale) == "expired"
