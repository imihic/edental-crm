from testing import fake_email

import pytest
import sqlalchemy.exc
from sqlalchemy import select, text

from app.identity import find_account_for_login, list_memberships
from app.identity.models import Account, Role, StaffMember
from app.platform.db import set_tenant_context


def test_find_account_ignores_case_and_whitespace_without_context(app_session, make_account):
    a = make_account(fake_email('testa', 'clinic.example.test'), totp_secret="TEST" * 4)
    found = find_account_for_login(app_session, f"  {fake_email('Testa', 'Clinic.example.test')} ")
    assert found.id == a.id and found.totp_enabled and found.password_hash == a.password_hash
    assert found.totp_secret_encrypted == a.totp_secret_encrypted


def test_find_unknown_returns_none(app_session):
    assert find_account_for_login(app_session, fake_email('nobody', 'x.example.test')) is None


def test_account_email_unique_any_case(make_account):
    make_account(fake_email('testa', 'clinic.example.test'))
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        make_account(fake_email('TESTA', 'clinic.example.test'))


def test_one_account_two_orgs_memberships(app_session, make_org, make_staff, make_account):
    acc = make_account(fake_email('dr', 'x.example.test'))
    a, b = make_org("Alpha"), make_org("Beta")
    make_staff(b, acc, roles=(Role.DENTIST, Role.CLINIC_MANAGER))
    make_staff(a, acc, roles=(Role.DENTIST,))
    ms = list_memberships(app_session, acc.id)
    assert [m.organization_name for m in ms] == ["Alpha", "Beta"]
    assert {m.organization_id for m in ms} == {a.id, b.id}


def test_inactive_staff_not_listed_as_membership(app_session, make_org, make_staff, make_account):
    acc = make_account(fake_email('dr', 'x.example.test'))
    make_staff(make_org("Alpha"), acc, is_active=False)
    make_staff(make_org("Beta"), acc)
    assert [m.organization_name for m in list_memberships(app_session, acc.id)] == ["Beta"]


def test_staff_requires_at_least_one_role(make_org, make_staff):
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        make_staff(make_org("A"), fake_email('a', 'x.example.test'), roles=())


def test_staff_unique_per_account_and_org(make_org, make_staff, make_account):
    acc, org = make_account(fake_email('a', 'x.example.test')), make_org("A")
    make_staff(org, acc)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        make_staff(org, acc)


def test_roles_stored_as_lowercase_strings(make_org, make_staff, owner_engine):
    make_staff(make_org("A"), fake_email('a', 'x.example.test'), roles=(Role.DENTIST, Role.CLINIC_MANAGER))
    with owner_engine.connect() as c:
        assert c.execute(text("SELECT roles::text[] FROM staff_members")).scalar_one() == [
            "dentist",
            "clinic_manager",
        ]


def test_rls_hides_other_orgs_staff_and_accounts(app_session, make_org, make_staff):
    a, b = make_org("A"), make_org("B")
    make_staff(a, fake_email('a', 'x.example.test'))
    make_staff(b, fake_email('b', 'x.example.test'))
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    assert [s.account.email for s in app_session.scalars(select(StaffMember))] == [fake_email('a', 'x.example.test')]
    assert [x.email for x in app_session.scalars(select(Account))] == [fake_email('a', 'x.example.test')]


def test_account_sees_itself_without_org(app_session, make_org, make_staff, make_account):
    acc = make_account(fake_email('me', 'x.example.test'))
    make_account(fake_email('other', 'x.example.test'))
    set_tenant_context(app_session, organization_id=None, account_id=acc.id)
    assert [x.email for x in app_session.scalars(select(Account))] == [fake_email('me', 'x.example.test')]


def test_staff_clinics_rls_and_relationship(app_session, make_org, make_clinic, make_staff):
    a, b = make_org("A"), make_org("B")
    ca, cb = make_clinic(a, "A1"), make_clinic(b, "B1")
    make_staff(a, fake_email('a', 'x.example.test'), clinics=(ca,))
    make_staff(b, fake_email('b', 'x.example.test'), clinics=(cb,))
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    (staff,) = app_session.scalars(select(StaffMember)).all()
    assert [c.name for c in staff.clinics] == ["A1"]
    assert app_session.execute(text("SELECT count(*) FROM staff_clinics")).scalar_one() == 1


def test_totp_secret_not_stored_in_plaintext(make_account, owner_engine):
    make_account(fake_email('a', 'x.example.test'), totp_secret="TEST" * 4)
    with owner_engine.connect() as c:
        stored = c.execute(text("SELECT totp_secret_encrypted FROM accounts")).scalar_one()
    assert stored and "TEST" * 4 not in stored


def test_app_cannot_delete_accounts(app_session, make_account):
    make_account(fake_email('a', 'x.example.test'))
    with pytest.raises(sqlalchemy.exc.ProgrammingError):
        app_session.execute(text("DELETE FROM accounts"))


def test_staff_clinics_rejects_cross_org_links(make_org, make_clinic, make_staff, owner_engine):
    a, b = make_org("A"), make_org("B")
    ca, cb = make_clinic(a, "A1"), make_clinic(b, "B1")
    sa, sb = make_staff(a, fake_email('a', 'x.example.test')), make_staff(b, fake_email('b', 'x.example.test'))
    for org, staff, clinic in ((a, sa, cb), (a, sb, ca), (b, sa, cb), (b, sb, ca)):
        with pytest.raises(sqlalchemy.exc.IntegrityError), owner_engine.begin() as c:
            c.execute(
                text("INSERT INTO staff_clinics VALUES (:o, :s, :c)"),
                {"o": org.id, "s": staff.id, "c": clinic.id},
            )


def test_org_context_cannot_update_account_credentials(app_session, make_org, make_staff, owner_engine):
    org = make_org("A")
    staff = make_staff(org, fake_email('a', 'x.example.test'))
    set_tenant_context(app_session, organization_id=org.id, account_id=None)
    result = app_session.execute(
        text("UPDATE accounts SET password_hash = 'evil' WHERE id = :i"), {"i": staff.account_id}
    )
    assert result.rowcount == 0
    with owner_engine.connect() as c:
        assert c.execute(text("SELECT password_hash FROM accounts")).scalar_one() != "evil"


def test_account_can_update_itself(app_session, make_account, owner_engine):
    acc = make_account(fake_email('a', 'x.example.test'))
    set_tenant_context(app_session, organization_id=None, account_id=acc.id)
    result = app_session.execute(
        text("UPDATE accounts SET password_hash = 'new' WHERE id = :i"), {"i": acc.id}
    )
    app_session.commit()
    assert result.rowcount == 1
    with owner_engine.connect() as c:
        assert c.execute(text("SELECT password_hash FROM accounts")).scalar_one() == "new"


def test_app_cannot_change_staff_account_or_org(app_session, make_org, make_staff, make_account):
    org = make_org("A")
    make_staff(org, fake_email('a', 'x.example.test'))
    other = make_account(fake_email('o', 'x.example.test'))
    set_tenant_context(app_session, organization_id=org.id, account_id=None)
    with pytest.raises(sqlalchemy.exc.ProgrammingError):
        app_session.execute(text("UPDATE staff_members SET account_id = :a"), {"a": other.id})


def test_app_can_update_staff_allowed_columns(app_session, make_org, make_staff):
    org = make_org("A")
    make_staff(org, fake_email('a', 'x.example.test'))
    set_tenant_context(app_session, organization_id=org.id, account_id=None)
    n = app_session.execute(text("UPDATE staff_members SET full_name = 'N', is_active = false")).rowcount
    assert n == 1
