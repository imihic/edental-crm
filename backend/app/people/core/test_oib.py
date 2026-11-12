from app.people.core.oib import is_valid_oib, mask_oib


def test_oib_checksum():
    assert is_valid_oib("11111111119") and not is_valid_oib("11111111110") and not is_valid_oib("1234")


def test_oib_rejects_non_digits():
    assert not is_valid_oib("1111111111a")


def test_mask_oib():
    assert mask_oib("11111111119") == "*******1119"
