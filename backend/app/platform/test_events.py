from dataclasses import dataclass
from uuid import uuid4

import pytest

from app.platform.events import DomainEvent, clear_subscribers, publish, subscribe


@dataclass(frozen=True)
class Ping(DomainEvent):
    n: int = 0


@dataclass(frozen=True)
class Other(DomainEvent):
    pass


def test_publish_runs_handlers_in_order_in_same_transaction(app_session):
    seen = []
    subscribe(Ping, lambda s, e: seen.append(("a", s, e.n)))
    subscribe(Ping, lambda s, e: seen.append(("b", s, e.n)))
    subscribe(Other, lambda s, e: seen.append(("other", s, 0)))
    publish(app_session, Ping(organization_id=uuid4(), n=7))
    assert seen == [("a", app_session, 7), ("b", app_session, 7)]


def test_handler_exception_propagates(app_session):
    def boom(s, e):
        raise RuntimeError("nope")

    subscribe(Ping, boom)
    with pytest.raises(RuntimeError):
        publish(app_session, Ping(organization_id=uuid4()))


def test_clear_subscribers(app_session):
    seen = []
    subscribe(Ping, lambda s, e: seen.append(1))
    clear_subscribers()
    publish(app_session, Ping(organization_id=uuid4()))
    assert seen == []
