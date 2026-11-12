from sqlalchemy import ColumnElement, func, or_

from app.people.core.phones import phone_search_digits

TRIGRAM_THRESHOLD = 0.3


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_predicate(model, q: str) -> ColumnElement | None:
    q = q.strip()
    if not q:
        return None
    needle = func.f_unaccent(func.lower(q))
    like = func.concat("%", func.f_unaccent(func.lower(_escape_like(q))), "%")
    matches = [
        model.search_text.ilike(like, escape="\\"),
        func.word_similarity(needle, model.search_text) > TRIGRAM_THRESHOLD,
    ]
    phone = phone_search_digits(q)
    if phone is not None:
        matches.append(model.phone_e164 == phone)
    return or_(*matches)
