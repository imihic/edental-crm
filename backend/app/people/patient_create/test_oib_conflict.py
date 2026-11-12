from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError

from app.people.patient_service import is_oib_conflict


def _error(constraint):
    return IntegrityError("stmt", {}, SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint)))


def test_only_the_oib_unique_index_counts_as_an_oib_conflict():
    assert is_oib_conflict(_error("uq_patients_org_oib"))
    assert not is_oib_conflict(_error("ck_patients_language"))
    assert not is_oib_conflict(IntegrityError("stmt", {}, Exception("no diag")))
