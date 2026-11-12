import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.models import Clinic
from app.platform.db import get_session, set_tenant_context
from app.platform.errors import ApiError


@pytest.fixture
def write_routes(app, make_org):
    org = make_org("A")

    def write():
        s = get_session()
        set_tenant_context(s, organization_id=org.id, account_id=None)
        s.add(Clinic(organization_id=org.id, name="C"))
        s.flush()

    @app.get("/w/ok")
    def ok():
        write()
        return {"ok": True}

    @app.get("/w/conflict")
    def conflict():
        write()
        raise ApiError(409, "conflict")

    @app.get("/w/401")
    def unauthorized():
        write()
        return {"error": "unauthorized"}, 401

    @app.get("/w/boom")
    def boom():
        write()
        raise RuntimeError("x")

    return org


def _names(owner_engine):
    with Session(owner_engine) as s:
        return s.scalars(select(Clinic.name)).all()


def test_success_commits(client, owner_engine, write_routes):
    assert client.get("/w/ok").status_code == 200
    assert _names(owner_engine) == ["C"]


def test_api_error_rolls_back(client, owner_engine, write_routes):
    r = client.get("/w/conflict")
    assert (r.status_code, r.get_json()) == (409, {"error": "conflict"})
    assert _names(owner_engine) == []


def test_returned_401_commits(client, owner_engine, write_routes):
    assert client.get("/w/401").status_code == 401
    assert _names(owner_engine) == ["C"]


def test_unhandled_exception_rolls_back(client, owner_engine, write_routes):
    r = client.get("/w/boom")
    assert (r.status_code, r.get_json()) == (500, {"error": "internal_error"})
    assert _names(owner_engine) == []
