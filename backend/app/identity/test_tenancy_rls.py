from uuid import uuid4

import pytest
import sqlalchemy.exc
from sqlalchemy import select

from app.identity.models import Clinic, Organization
from app.platform.db import set_tenant_context


def test_sees_only_own_org(app_session, make_org, make_clinic):
    a, b = make_org("A"), make_org("B")
    make_clinic(a, "A1")
    make_clinic(b, "B1")
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    assert [c.name for c in app_session.scalars(select(Clinic))] == ["A1"]
    assert [o.name for o in app_session.scalars(select(Organization))] == ["A"]


def test_no_context_sees_nothing_and_does_not_raise(app_session, make_org, make_clinic):
    make_clinic(make_org("A"), "A1")
    assert app_session.scalars(select(Clinic)).all() == []


def test_cannot_insert_into_other_org(app_session, make_org):
    a, b = make_org("A"), make_org("B")
    set_tenant_context(app_session, organization_id=a.id, account_id=None)
    app_session.add(Clinic(id=uuid4(), organization_id=b.id, name="X"))
    with pytest.raises(sqlalchemy.exc.ProgrammingError):
        app_session.flush()


def test_org_defaults(make_org):
    o = make_org("A")
    assert (o.timezone, o.currency, o.locale) == ("Europe/Zagreb", "EUR", "en")
