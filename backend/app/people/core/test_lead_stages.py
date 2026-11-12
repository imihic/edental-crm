import itertools

import pytest

from app.people.core.lead_stages import ALLOWED, STAGES, InvalidTransition, LostReasonRequired, transition


@pytest.mark.parametrize("current,target", list(itertools.product(STAGES, STAGES)))
def test_stage_machine_table(current, target):
    if target in ALLOWED[current]:
        transition(current, target, lost_reason="price" if target == "lost" else None)
    else:
        with pytest.raises(InvalidTransition):
            transition(current, target, lost_reason="price")


def test_table_matches_the_spec():
    assert ALLOWED == {
        "new": {"contacted", "consultation_booked", "lost"},
        "contacted": {"consultation_booked", "lost"},
        "consultation_booked": {"contacted", "lost"},
        "lost": {"new"},
        "converted": set(),
    }


@pytest.mark.parametrize("reason", [None, ""])
def test_lost_requires_reason(reason):
    with pytest.raises(LostReasonRequired):
        transition("new", "lost", lost_reason=reason)


def test_converted_is_never_a_target():
    assert all("converted" not in targets for targets in ALLOWED.values())
