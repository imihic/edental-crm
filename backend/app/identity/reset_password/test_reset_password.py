from testing import fake_email, fake_password

import pyotp
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.identity import Role
from app.identity.reset_password.handler import reset_password
from app.platform.db import get_session

NEW = fake_password('reset')


@pytest.fixture(autouse=True)
def _clean_db(owner_engine):
    pass


def _reset(app, **kw):
    args = dict(email=fake_email('mgr', 'clinic.example.test'), new_password=NEW, reset_totp=False)
    args.update(kw)
    with app.app_context():
        reset_password(get_session(), **args)


def _login(client, password):
    return client.post("/api/auth/login", json={"email": fake_email('mgr', 'clinic.example.test'), "password": password})


def test_reset_password_allows_new_password_only(app, client, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.RECEPTIONIST,))
    _reset(app, email=f" {fake_email('MGR', 'clinic.example.test')} ")
    assert _login(client, fake_password('account')).status_code == 401
    assert _login(client, NEW).status_code == 200


def test_reset_totp_unfences_enrollment(app, client, make_org, make_account, make_staff):
    acc = make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=pyotp.random_base32())
    make_staff(make_org("Smile"), acc, roles=(Role.CLINIC_MANAGER,))
    _reset(app, reset_totp=True)
    assert _login(client, NEW).get_json() == {"status": "ok"}
    assert client.get("/api/auth/me").get_json()["totp_enrollment_required"] is True


def test_totp_kept_without_flag(app, client, make_org, make_account, make_staff):
    acc = make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=pyotp.random_base32())
    make_staff(make_org("Smile"), acc, roles=(Role.CLINIC_MANAGER,))
    _reset(app)
    assert _login(client, NEW).get_json() == {"status": "totp_required"}


def test_audit_per_member_org(app, owner_engine, make_org, make_account, make_staff):
    acc = make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=pyotp.random_base32())
    a, b = make_org("Alpha"), make_org("Beta")
    sa, sb = make_staff(a, acc, roles=(Role.DENTIST,)), make_staff(b, acc, roles=(Role.DENTIST,))
    _reset(app, reset_totp=True)
    with Session(owner_engine) as s:
        rows = s.execute(
            text(
                "SELECT organization_id, staff_member_id, account_id, action, entity_type, entity_id, detail "
                "FROM audit_entries"
            )
        ).all()
    assert {(r.organization_id, r.staff_member_id) for r in rows} == {(a.id, sa.id), (b.id, sb.id)}
    for r in rows:
        assert (r.action, r.entity_type, r.entity_id, r.account_id) == ("update", "account", acc.id, acc.id)
        assert r.detail == {"fields": ["password", "totp"]}


def test_reset_unknown_email(app):
    with pytest.raises(ValueError, match="account_not_found"):
        _reset(app, email=fake_email('nobody', 'x.example.test'))


def test_reset_short_password(app, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'))
    with pytest.raises(ValueError, match="password_too_short"):
        _reset(app, new_password="short")


def test_cli_reset(app, client, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'))
    r = app.test_cli_runner().invoke(
        args=["reset-password", "--email", fake_email('mgr', 'clinic.example.test'), "--reset-totp"], input=f"{NEW}\n{NEW}\n"
    )
    assert r.exit_code == 0, r.output
    assert NEW not in r.output
    assert _login(client, NEW).status_code == 200


def test_cli_unknown_email_is_one_line_error(app):
    r = app.test_cli_runner().invoke(args=["reset-password", "--email", fake_email('x', 'y.example.test')], input=f"{NEW}\n{NEW}\n")
    assert r.exit_code == 1 and "account_not_found" in r.output and "Traceback" not in r.output


def test_reset_revokes_a_signed_in_session(app, client, login, make_org, make_staff):
    make_staff(make_org("Smile"), fake_email('mgr', 'clinic.example.test'), roles=(Role.RECEPTIONIST,))
    login(client, fake_email('mgr', 'clinic.example.test'))
    _reset(app)
    r = client.get("/api/auth/me")
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})
    with client.session_transaction() as s:
        assert "account_id" not in s and "staff_member_id" not in s


def test_reset_revokes_a_session_choosing_an_organization(app, client, make_org, make_staff, make_account):
    acc = make_account(fake_email('mgr', 'clinic.example.test'))
    make_staff(make_org("A"), acc)
    make_staff(make_org("B"), acc)
    assert _login(client, fake_password('account')).get_json()["status"] == "choose_organization"
    _reset(app)
    r = client.get("/api/auth/organizations")
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})
    with client.session_transaction() as s:
        assert "account_id" not in s


def test_reset_revokes_a_pending_totp_session(app, client, make_org, make_account, make_staff):
    secret = pyotp.random_base32()
    acc = make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=secret)
    make_staff(make_org("Smile"), acc, roles=(Role.CLINIC_MANAGER,))
    assert _login(client, fake_password('account')).get_json() == {"status": "totp_required"}
    _reset(app)
    r = client.post("/api/auth/totp", json={"code": pyotp.TOTP(secret).now()})
    assert (r.status_code, r.get_json()) == (401, {"error": "unauthenticated"})
    with client.session_transaction() as s:
        assert "pending_account_id" not in s
