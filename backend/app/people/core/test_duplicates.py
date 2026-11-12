from testing import fake_email

from datetime import date

from app.people.core.duplicates import Candidate, match_reasons


def cand(**kw) -> Candidate:
    base = dict(first_name="Testa", last_name="Testić", date_of_birth=None, email=None, oib=None)
    return Candidate(**{**base, **kw})


def test_oib_match_needs_both_present():
    assert match_reasons(cand(oib="11111111119"), cand(oib="11111111119")) == ["oib"]
    assert match_reasons(cand(oib=None), cand(oib=None)) == []


def test_name_and_birth_date_ignores_diacritics_and_case():
    a = cand(first_name="Testana", last_name="Těstić", date_of_birth=date(1990, 1, 2))
    b = cand(first_name="TESTANA", last_name="testic", date_of_birth=date(1990, 1, 2))
    assert match_reasons(a, b) == ["name_and_birth_date"]


def test_same_name_without_birth_date_is_not_a_match():
    assert match_reasons(cand(), cand()) == []
    assert match_reasons(cand(date_of_birth=date(1990, 1, 2)), cand(date_of_birth=date(1991, 1, 2))) == []


def test_email_is_case_insensitive():
    assert match_reasons(cand(email=fake_email('A', 'x.example.test')), cand(first_name="Bo", email=fake_email('a', 'X.example.test'))) == ["email"]


def test_reasons_can_combine_in_stable_order():
    a = cand(oib="11111111119", email=fake_email('a', 'x.example.test'), date_of_birth=date(1990, 1, 2))
    assert match_reasons(a, a) == ["oib", "name_and_birth_date", "email"]
