STAGES = ("new", "contacted", "consultation_booked", "converted", "lost")
LOST_REASONS = ("price", "distance", "chose_other_clinic", "no_response", "not_needed", "other")

ALLOWED: dict[str, set[str]] = {
    "new": {"contacted", "consultation_booked", "lost"},
    "contacted": {"consultation_booked", "lost"},
    "consultation_booked": {"contacted", "lost"},
    "lost": {"new"},
    "converted": set(),
}


class InvalidTransition(ValueError):
    pass


class LostReasonRequired(ValueError):
    pass


def transition(current: str, target: str, *, lost_reason: str | None) -> None:
    if target not in ALLOWED.get(current, set()):
        raise InvalidTransition(f"{current} -> {target}")
    if target == "lost" and not lost_reason:
        raise LostReasonRequired(target)
