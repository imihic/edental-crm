import pytest

from app.people.core.phones import InvalidPhone, normalize_phone, phone_search_digits


@pytest.mark.parametrize(
    ("raw", "region"),
    [("+1 202 555 0100", "HR"), ("0012025550100", "HR"),
     ("00 1/202-555-0100", "HR"), ("202/555-0100", "US")],
)
def test_normalize_phone_variants(raw, region):
    assert normalize_phone(raw, region) == "+12025550100"


def test_normalize_phone_rejects_garbage():
    with pytest.raises(InvalidPhone):
        normalize_phone("abc")


def test_phone_search_digits():
    assert phone_search_digits("00 1 202 555 0100") == "+12025550100"
    assert phone_search_digits("Testić") is None
