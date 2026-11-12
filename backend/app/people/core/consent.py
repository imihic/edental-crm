from collections.abc import Iterable
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

State = Literal["granted", "withdrawn", "unknown"]
PURPOSES = ("marketing",)


class Entry(Protocol):
    id: UUID
    purpose: str
    granted: bool
    recorded_at: datetime


def order_key(entry: Entry) -> tuple[datetime, UUID]:
    return (entry.recorded_at, entry.id)


def current_state(entries: Iterable[Entry]) -> dict[str, State]:
    state: dict[str, State] = {purpose: "unknown" for purpose in PURPOSES}
    for entry in sorted(entries, key=order_key):
        state[entry.purpose] = "granted" if entry.granted else "withdrawn"
    return state
