from app.people.core.names import name_key, normalize_name


def test_name_key_ignores_diacritics_and_case():
    assert name_key(" Těstić ", "ĐTESTA") == name_key("testic", "dtesta")


def test_normalize_name_collapses_whitespace():
    assert normalize_name("  Testa   Testm ") == "Testa Testm"
