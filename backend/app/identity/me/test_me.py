from testing import fake_email

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.identity import Role
from app.identity.models import StaffMember


def test_me_requires_bound_staff_member(client):
    r = client.get("/api/auth/me")
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})


def test_me_shape(client, login, make_org, make_clinic, make_staff):
    org = make_org("Smile")
    c2, c1 = make_clinic(org, "Zapad"), make_clinic(org, "Centar")
    unassigned = make_clinic(org, "Sjever")
    make_clinic(make_org("Other"), "Other Clinic")
    staff = make_staff(
        org, fake_email('testa', 'clinic.example.test'), roles=(Role.DENTIST, Role.CLINIC_MANAGER), clinics=[c2, c1], full_name="Testa"
    )
    me = login(client, fake_email('testa', 'clinic.example.test'))
    assert me == {
        "account": {"id": str(staff.account_id), "email": fake_email('testa', 'clinic.example.test')},
        "staff": {"id": str(staff.id), "full_name": "Testa", "roles": ["dentist", "clinic_manager"]},
        "organization": {
            "id": str(org.id),
            "name": "Smile",
            "timezone": "Europe/Zagreb",
            "currency": "EUR",
            "locale": "en",
        },
        "clinics": [{"id": str(c1.id), "name": "Centar"}, {"id": str(c2.id), "name": "Zapad"}],
        "organization_clinics": [
            {"id": str(c1.id), "name": "Centar"},
            {"id": str(unassigned.id), "name": "Sjever"},
            {"id": str(c2.id), "name": "Zapad"},
        ],
        "organizations_count": 1,
        "totp_enrollment_required": True,
    }


def test_deactivated_staff_session_is_revoked(client, login, owner_engine, make_org, make_staff):
    staff = make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'))
    login(client, fake_email('testa', 'clinic.example.test'))
    with Session(owner_engine) as s:
        s.execute(update(StaffMember).where(StaffMember.id == staff.id).values(is_active=False))
        s.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert client.get_cookie("crm_session") is None
    with Session(owner_engine) as s:
        s.execute(update(StaffMember).where(StaffMember.id == staff.id).values(is_active=True))
        s.commit()
    assert client.get("/api/auth/me").status_code == 401


def _signed_in_at(client, login, make_org, make_staff, monkeypatch):
    import app.identity.session as session_mod

    t0 = 1_800_000_000.0
    monkeypatch.setattr(session_mod, "now", lambda: t0)
    make_staff(make_org("Smile"), fake_email('testa', 'clinic.example.test'))
    login(client, fake_email('testa', 'clinic.example.test'))
    return session_mod, t0


def test_session_valid_until_twelve_hours_after_sign_in(client, login, make_org, make_staff, monkeypatch):
    session_mod, t0 = _signed_in_at(client, login, make_org, make_staff, monkeypatch)
    monkeypatch.setattr(session_mod, "now", lambda: t0 + 11 * 3600 + 59 * 60)
    assert client.get("/api/auth/me").status_code == 200


def test_session_has_absolute_twelve_hour_cap(client, login, make_org, make_staff, monkeypatch):
    session_mod, t0 = _signed_in_at(client, login, make_org, make_staff, monkeypatch)
    monkeypatch.setattr(session_mod, "now", lambda: t0 + 6 * 3600)
    assert client.get("/api/auth/me").status_code == 200
    monkeypatch.setattr(session_mod, "now", lambda: t0 + 12 * 3600 + 1)
    assert client.get("/api/auth/me").status_code == 401
    assert client.get_cookie("crm_session") is None


def test_switching_organization_keeps_the_original_sign_in_time(
    client, login, csrf, make_org, make_staff, make_account, monkeypatch
):
    import app.identity.session as session_mod

    t0 = 1_800_000_000.0
    monkeypatch.setattr(session_mod, "now", lambda: t0)
    acc = make_account(fake_email('dr', 'x.example.test'))
    a, b = make_org("Alpha"), make_org("Beta")
    make_staff(a, acc, roles=(Role.DENTIST,))
    make_staff(b, acc, roles=(Role.DENTIST,))
    login(client, fake_email('dr', 'x.example.test'), organization_id=a.id)
    monkeypatch.setattr(session_mod, "now", lambda: t0 + 11 * 3600)
    r = client.post("/api/auth/organization", json={"organization_id": str(b.id)}, headers=csrf(client))
    assert r.status_code == 200
    monkeypatch.setattr(session_mod, "now", lambda: t0 + 12 * 3600 + 1)
    assert client.get("/api/auth/me").status_code == 401


def test_new_password_login_resets_the_sign_in_time(client, login, make_org, make_staff, monkeypatch):
    session_mod, t0 = _signed_in_at(client, login, make_org, make_staff, monkeypatch)
    monkeypatch.setattr(session_mod, "now", lambda: t0 + 11 * 3600)
    login(client, fake_email('testa', 'clinic.example.test'))
    monkeypatch.setattr(session_mod, "now", lambda: t0 + 12 * 3600 + 1)
    assert client.get("/api/auth/me").status_code == 200
