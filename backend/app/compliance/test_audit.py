from testing import fake_email

import pytest
import sqlalchemy.exc
from sqlalchemy import select, text

from app.compliance import AuditAction, record_audit
from app.compliance.models import AuditEntry
from app.platform.db import set_tenant_context


def test_record_and_read_back(app_session, make_org, make_staff):
    org = make_org("A")
    staff = make_staff(org, fake_email('testa', 'clinic.example.test'))
    set_tenant_context(app_session, organization_id=org.id, account_id=staff.account_id)
    record_audit(
        app_session,
        organization_id=org.id,
        action=AuditAction.LOGIN,
        entity_type="staff_member",
        entity_id=staff.id,
        staff_member_id=staff.id,
        account_id=staff.account_id,
    )
    app_session.flush()
    entry = app_session.scalars(select(AuditEntry)).one()
    assert entry.action == AuditAction.LOGIN
    assert entry.entity_id == staff.id
    assert entry.staff_member_id == staff.id
    assert entry.detail == {}
    assert entry.occurred_at is not None


def test_detail_is_stored(app_session, make_org):
    org = make_org("A")
    set_tenant_context(app_session, organization_id=org.id, account_id=None)
    record_audit(
        app_session,
        organization_id=org.id,
        action=AuditAction.LOGIN_FAILED,
        entity_type="account",
        detail={"reason": "bad_password"},
    )
    app_session.flush()
    assert app_session.scalars(select(AuditEntry)).one().detail == {"reason": "bad_password"}


@pytest.mark.parametrize(
    "sql", ["UPDATE audit_entries SET entity_type = 'x'", "DELETE FROM audit_entries"]
)
def test_app_role_cannot_update_or_delete(app_session, make_org, sql):
    org = make_org("A")
    set_tenant_context(app_session, organization_id=org.id, account_id=None)
    record_audit(app_session, organization_id=org.id, action=AuditAction.VIEW, entity_type="x")
    app_session.commit()
    set_tenant_context(app_session, organization_id=org.id, account_id=None)
    with pytest.raises(sqlalchemy.exc.ProgrammingError):
        app_session.execute(text(sql))
    app_session.rollback()


def test_other_org_cannot_read_entries(app_session, make_org):
    a, b = make_org("A"), make_org("B")
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    record_audit(app_session, organization_id=a.id, action=AuditAction.VIEW, entity_type="x")
    app_session.commit()
    set_tenant_context(app_session, organization_id=b.id, account_id=None)
    assert app_session.scalars(select(AuditEntry)).all() == []


def test_cannot_write_entry_for_other_org(app_session, make_org):
    a, b = make_org("A"), make_org("B")
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    record_audit(app_session, organization_id=b.id, action=AuditAction.VIEW, entity_type="x")
    with pytest.raises(sqlalchemy.exc.ProgrammingError):
        app_session.flush()


def test_entry_cannot_reference_other_orgs_staff(app_session, make_org, make_staff):
    a, b = make_org("A"), make_org("B")
    staff_b = make_staff(b, fake_email('b', 'clinic.example.test'))
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    record_audit(
        app_session,
        organization_id=a.id,
        action=AuditAction.VIEW,
        entity_type="x",
        staff_member_id=staff_b.id,
    )
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        app_session.flush()
