from dataclasses import dataclass
from datetime import date

from app.people.core.names import name_key


@dataclass(frozen=True)
class Candidate:
    first_name: str
    last_name: str
    date_of_birth: date | None
    email: str | None
    oib: str | None


def match_reasons(a: Candidate, b: Candidate) -> list[str]:
    reasons = []
    if a.oib and b.oib and a.oib == b.oib:
        reasons.append("oib")
    if (
        a.date_of_birth is not None
        and a.date_of_birth == b.date_of_birth
        and name_key(a.first_name, a.last_name) == name_key(b.first_name, b.last_name)
    ):
        reasons.append("name_and_birth_date")
    if a.email and b.email and a.email.lower() == b.email.lower():
        reasons.append("email")
    return reasons
