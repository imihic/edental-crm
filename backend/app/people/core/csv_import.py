import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from app.people.core.names import normalize_name
from app.people.core.oib import is_valid_oib
from app.people.core.phones import InvalidPhone, normalize_phone

ALIASES = {
    "ime": "first_name",
    "firstname": "first_name",
    "prezime": "last_name",
    "lastname": "last_name",
    "datumrodjenja": "date_of_birth",
    "datumrodenja": "date_of_birth",
    "dateofbirth": "date_of_birth",
    "telefon": "phone",
    "mobitel": "phone",
    "phone": "phone",
    "email": "email",
    "eposta": "email",
    "oib": "oib",
    "adresa": "address",
    "address": "address",
    "klinika": "clinic",
    "clinic": "clinic",
    "napomena": "notes",
    "notes": "notes",
}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s.]+$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_HR_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\.?$")
MAX_LENGTHS = {"first_name": 100, "last_name": 100, "address": 300, "notes": 500, "email": 254}


class TooManyRows(Exception):
    pass


@dataclass
class ParsedRow:
    line: int
    values: dict
    errors: list[str] = field(default_factory=list)


@dataclass
class ParsedFile:
    rows: list[ParsedRow]
    errors: list[str] = field(default_factory=list)
    ignored_columns: list[str] = field(default_factory=list)


def fold(value: str) -> str:
    value = value.strip().lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def _header_key(header: str) -> str:
    return re.sub(r"[\s_\-]+", "", fold(header))


def decode(raw: bytes) -> str | None:
    if b"\x00" in raw:
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1250", errors="replace")
    if text.count("\ufffd") > len(text) * 0.01:
        return None
    return text


def parse_date(value: str, today: date | None = None) -> date | None:
    if m := _ISO_DATE.match(value):
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
    elif m := _HR_DATE.match(value):
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
    else:
        return None
    try:
        parsed = date(y, mo, d)
    except ValueError:
        return None
    return None if parsed > (today or date.today()) else parsed


def _validate(line: int, cells: dict) -> ParsedRow:
    errors: list[str] = []
    values: dict = {}

    def text(key: str) -> str | None:
        return (cells.get(key) or "").strip() or None

    for key in ("first_name", "last_name"):
        v = normalize_name(cells.get(key) or "")
        if not v:
            errors.append(f"missing_{key}")
        elif len(v) > MAX_LENGTHS[key]:
            errors.append(f"invalid_{key}")
        values[key] = v or None

    raw_dob = text("date_of_birth")
    values["date_of_birth"] = None
    if raw_dob:
        parsed = parse_date(raw_dob)
        if parsed is None:
            errors.append("invalid_date")
        else:
            values["date_of_birth"] = parsed.isoformat()

    raw_phone = text("phone")
    values["phone"] = None
    if raw_phone:
        try:
            values["phone"] = normalize_phone(raw_phone)
        except InvalidPhone:
            errors.append("invalid_phone")

    email = text("email")
    values["email"] = email
    if email and (not _EMAIL.match(email) or len(email) > MAX_LENGTHS["email"]):
        errors.append("invalid_email")

    oib = text("oib")
    values["oib"] = oib
    if oib and not is_valid_oib(oib):
        errors.append("invalid_oib")

    for key in ("address", "notes"):
        v = text(key)
        values[key] = v
        if v and len(v) > MAX_LENGTHS[key]:
            errors.append(f"invalid_{key}")
    values["clinic"] = text("clinic")
    return ParsedRow(line=line, values=values, errors=errors)


def parse_patients_csv(raw: bytes, *, max_rows: int | None = None) -> ParsedFile:
    content = decode(raw)
    if content is None:
        return ParsedFile(rows=[], errors=["unsupported_file"])
    try:
        return _parse(content, max_rows)
    except csv.Error:
        return ParsedFile(rows=[], errors=["invalid_file"])


def _parse(content: str, max_rows: int | None) -> ParsedFile:
    lines = content.splitlines()
    header_line = next((ln for ln in lines if ln.strip()), None)
    if header_line is None:
        return ParsedFile(rows=[], errors=["empty_file"])
    delimiter = ";" if header_line.count(";") > header_line.count(",") else ","

    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    columns: dict[int, str] = {}
    ignored: list[str] = []
    header_seen = False
    rows: list[ParsedRow] = []
    previous_end = 0
    for record in reader:
        start, previous_end = previous_end + 1, reader.line_num
        if not header_seen:
            if not any(c.strip() for c in record):
                continue
            header_seen = True
            for idx, name in enumerate(record):
                target = ALIASES.get(_header_key(name))
                if target is None or target in columns.values():
                    if name.strip():
                        ignored.append(name.strip())
                else:
                    columns[idx] = target
            missing = [f for f in ("first_name", "last_name") if f not in columns.values()]
            if missing:
                return ParsedFile(rows=[], errors=[f"missing_column_{f}" for f in missing], ignored_columns=ignored)
            continue
        if not any(c.strip() for c in record):
            continue
        if max_rows is not None and len(rows) >= max_rows:
            raise TooManyRows
        cells = {columns[i]: record[i] for i in columns if i < len(record)}
        rows.append(_validate(start, cells))
    return ParsedFile(rows=rows, ignored_columns=ignored)
