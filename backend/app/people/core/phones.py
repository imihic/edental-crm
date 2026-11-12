import re

import phonenumbers

_ALLOWED = re.compile(r"^[0-9\s+()/.\-]+$")


class InvalidPhone(ValueError):
    pass


def normalize_phone(raw: str, region: str = "HR") -> str:
    if not _ALLOWED.match(raw):
        raise InvalidPhone(raw)
    try:
        number = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhone(raw) from exc
    if not phonenumbers.is_valid_number(number):
        raise InvalidPhone(raw)
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def phone_search_digits(raw: str) -> str | None:
    try:
        return normalize_phone(raw)
    except InvalidPhone:
        return None
