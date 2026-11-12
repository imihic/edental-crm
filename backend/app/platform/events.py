from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DomainEvent:
    organization_id: UUID


Handler = Callable[[Session, DomainEvent], None]
_subscribers: dict[type[DomainEvent], list[Handler]] = {}


def subscribe(event_type: type[DomainEvent], handler: Handler) -> None:
    _subscribers.setdefault(event_type, []).append(handler)


def publish(session: Session, event: DomainEvent) -> None:
    for handler in list(_subscribers.get(type(event), ())):
        handler(session, event)


def clear_subscribers() -> None:
    _subscribers.clear()
