from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.people.core.csv_import import ParsedFile, fold
from app.people.core.duplicates import Candidate, match_reasons
from app.people.core.names import name_key
from app.people.duplicates import find_possible_duplicates
from app.people.models import PatientImport
from app.people.schemas import DuplicateOut

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
EXPIRY = timedelta(hours=24)


class ImportPath(BaseModel):
    import_id: UUID


class PreviewIn(BaseModel):
    filename: str = Field(max_length=255)
    content_base64: str


class CommitIn(BaseModel):
    include_duplicates: bool = False


class PreviewRowOut(BaseModel):
    line: int
    status: str
    errors: list[str]
    duplicates: list[DuplicateOut]
    in_file_duplicate_of_line: int | None


class PreviewOut(BaseModel):
    import_id: UUID
    rows: list[PreviewRowOut]
    ignored_columns: list[str]
    counts: dict[str, int]


class CommitOut(BaseModel):
    created: int
    skipped: int


class ImportItem(BaseModel):
    id: UUID
    filename: str
    status: str
    counts: dict[str, int]
    created_at: datetime
    committed_at: datetime | None


class ImportListOut(BaseModel):
    items: list[ImportItem]


def is_expired(imp: PatientImport) -> bool:
    return imp.status == "expired" or (imp.status == "previewed" and datetime.now(UTC) - imp.created_at > EXPIRY)


def blank_expired(session: Session) -> None:
    session.execute(
        text(
            """
            UPDATE patient_imports SET status = 'expired', rows = coalesce((
                SELECT jsonb_agg(jsonb_build_object(
                    'line', r.value -> 'line', 'status', r.value -> 'status', 'errors', r.value -> 'errors',
                    'in_file_duplicate_of_line', r.value -> 'in_file_duplicate_of_line'
                ) ORDER BY r.ord)
                FROM jsonb_array_elements(rows) WITH ORDINALITY AS r(value, ord)
            ), '[]'::jsonb)
            WHERE status = 'previewed' AND created_at < now() - interval '24 hours'
            """
        )
    )
    session.expire_all()


def clinics_by_name(session: Session) -> dict[str, UUID]:
    found: dict[str, UUID] = {}
    for clinic_id, name in session.execute(text("SELECT id, name FROM clinics ORDER BY name, id")):
        found.setdefault(fold(" ".join(name.split())), clinic_id)
    return found


def _candidate(values: dict) -> Candidate:
    dob = date.fromisoformat(values["date_of_birth"]) if values["date_of_birth"] else None
    return Candidate(values["first_name"], values["last_name"], dob, values["email"], values["oib"])


def analyse(session: Session, parsed: ParsedFile) -> list[dict]:
    clinics = clinics_by_name(session)
    by_oib: dict[str, list[int]] = {}
    by_email: dict[str, list[int]] = {}
    by_name_dob: dict[tuple[str, date], list[int]] = {}
    candidates: dict[int, Candidate] = {}
    out = []
    for row in parsed.rows:
        errors = list(row.errors)
        clinic_id = None
        if row.values["clinic"]:
            clinic_id = clinics.get(fold(" ".join(row.values["clinic"].split())))
            if clinic_id is None:
                errors.append("unknown_clinic")
        record = {
            "line": row.line,
            "values": row.values,
            "errors": errors,
            "clinic_id": str(clinic_id) if clinic_id else None,
            "status": "invalid",
            "duplicates": [],
            "in_file_duplicate_of_line": None,
            "oib_conflict": False,
        }
        out.append(record)
        if errors:
            continue
        cand = _candidate(row.values)
        record["in_file_duplicate_of_line"] = _earlier_match(cand, candidates, by_oib, by_email, by_name_dob)
        _register(row.line, cand, candidates, by_oib, by_email, by_name_dob)
        duplicates = find_possible_duplicates(session, cand)
        record["duplicates"] = [d.model_dump(mode="json") for d in duplicates]
        record["oib_conflict"] = any(d.kind == "patient" and "oib" in d.reasons for d in duplicates)
        is_dup = bool(duplicates) or record["in_file_duplicate_of_line"] is not None
        record["status"] = "duplicate" if is_dup else "valid"
    return out


def _earlier_match(cand, candidates, by_oib, by_email, by_name_dob) -> int | None:
    hits = []
    if cand.oib and cand.oib in by_oib:
        hits.append(by_oib[cand.oib][0])
    if cand.email and cand.email.lower() in by_email:
        hits.append(by_email[cand.email.lower()][0])
    if cand.date_of_birth is not None:
        key = (name_key(cand.first_name, cand.last_name), cand.date_of_birth)
        if key in by_name_dob:
            hits.append(by_name_dob[key][0])
    for line in sorted(hits):
        if match_reasons(cand, candidates[line]):
            return line
    return None


def _register(line, cand, candidates, by_oib, by_email, by_name_dob) -> None:
    candidates[line] = cand
    if cand.oib:
        by_oib.setdefault(cand.oib, []).append(line)
    if cand.email:
        by_email.setdefault(cand.email.lower(), []).append(line)
    if cand.date_of_birth is not None:
        by_name_dob.setdefault((name_key(cand.first_name, cand.last_name), cand.date_of_birth), []).append(line)


def counts_of(records: list[dict]) -> dict[str, int]:
    counts = {"total": len(records), "valid": 0, "invalid": 0, "duplicate": 0}
    for r in records:
        counts[r["status"]] += 1
    return counts
