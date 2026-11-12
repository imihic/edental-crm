from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.people.core.consent import current_state

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class E:
    id: UUID
    purpose: str
    granted: bool
    recorded_at: datetime


def uid(n: int) -> UUID:
    return UUID(int=n)


def test_no_entries_is_unknown():
    assert current_state([]) == {"marketing": "unknown"}


def test_latest_wins_regardless_of_input_order():
    grant = E(uid(1), "marketing", True, T0)
    withdraw = E(uid(2), "marketing", False, T0 + timedelta(days=1))
    assert current_state([withdraw, grant]) == {"marketing": "withdrawn"}
    regrant = E(uid(3), "marketing", True, T0 + timedelta(days=2))
    assert current_state([regrant, withdraw, grant]) == {"marketing": "granted"}


def test_id_breaks_ties_on_equal_time():
    a = E(uid(1), "marketing", True, T0)
    b = E(uid(2), "marketing", False, T0)
    assert current_state([a, b]) == {"marketing": "withdrawn"}
    assert current_state([b, a]) == {"marketing": "withdrawn"}
