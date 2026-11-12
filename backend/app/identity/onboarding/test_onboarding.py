from testing import fake_email, fake_password

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.identity import Role
from app.identity.onboarding.handler import create_organization
from app.platform.db import get_session

PW = "long enough pw 1"
CLI_ARGS = [
    "create-organization", "--name", "Smile", "--clinic", "Centar",
    "--manager-email", fake_email('m', 'smile.example.test'), "--manager-name", "Testg",
]


@pytest.fixture(autouse=True)
def _clean_db(owner_engine):
    pass


def _create(app, **kw):
    args = dict(
        name="Smile", clinic_name="Centar", manager_email=fake_email('m', 'smile.example.test'), manager_name="Testg", manager_password=PW
    )
    args.update(kw)
    with app.app_context():
        return create_organization(get_session(), **args)


def test_new_org_manager_can_sign_in_and_is_fenced(app, client, login):
    org = _create(app)
    me = login(client, fake_email('m', 'smile.example.test'), PW)
    assert me["staff"]["roles"] == ["clinic_manager"] and me["staff"]["full_name"] == "Testg"
    assert me["totp_enrollment_required"] is True
    assert [c["name"] for c in me["clinics"]] == ["Centar"]
    assert me["organization"]["id"] == str(org.id) and me["organization"]["name"] == "Smile"
    assert me["organization"]["timezone"] == "Europe/Zagreb"


def test_existing_account_gets_second_membership(app, client, login, make_org, make_staff):
    other = make_org("Other")
    make_staff(other, fake_email('m', 'smile.example.test'), roles=(Role.DENTIST,))
    org = _create(app, manager_password=None)
    r = client.post("/api/auth/login", json={"email": fake_email('m', 'smile.example.test'), "password": fake_password('account')})
    assert r.get_json()["status"] == "choose_organization"
    assert {o["name"] for o in r.get_json()["organizations"]} == {"Other", "Smile"}
    me = login(client, fake_email('m', 'smile.example.test'), organization_id=org.id)
    assert me["staff"]["roles"] == ["clinic_manager"]


def test_existing_account_with_password_rejected(app, make_org, make_staff, owner_engine):
    make_staff(make_org("Other"), fake_email('m', 'smile.example.test'))
    with pytest.raises(ValueError, match="account_exists"):
        _create(app)
    with Session(owner_engine) as s:
        assert s.execute(text("SELECT count(*) FROM organizations")).scalar_one() == 1


def test_short_password_rejected(app, owner_engine):
    with pytest.raises(ValueError, match="password_too_short"):
        _create(app, manager_password="short")
    with Session(owner_engine) as s:
        assert s.execute(text("SELECT count(*) FROM accounts")).scalar_one() == 0


def test_audits_recorded(app, owner_engine):
    org = _create(app)
    with Session(owner_engine) as s:
        rows = s.execute(text("SELECT action, entity_type, organization_id FROM audit_entries")).all()
    assert {(r.action, r.entity_type) for r in rows} == {
        ("create", "organization"),
        ("create", "clinic"),
        ("create", "staff_member"),
    }
    assert {r.organization_id for r in rows} == {org.id}


def test_cli_prints_org_id(app):
    r = app.test_cli_runner().invoke(args=CLI_ARGS, input=f"{PW}\n{PW}\n")
    assert r.exit_code == 0, r.output
    assert UUID(r.output.strip().splitlines()[-1])
    assert PW not in r.output


def test_cli_reuses_account_without_prompt(app, make_org, make_staff):
    make_staff(make_org("Other"), fake_email('m', 'smile.example.test'))
    r = app.test_cli_runner().invoke(args=CLI_ARGS)
    assert r.exit_code == 0, r.output
    assert "Reused existing account" in r.output
    assert UUID(r.output.strip().splitlines()[-1])


def test_cli_short_password_is_one_line_error(app):
    r = app.test_cli_runner().invoke(args=CLI_ARGS, input="short\nshort\n")
    assert r.exit_code == 1
    assert "password_too_short" in r.output and "Traceback" not in r.output
