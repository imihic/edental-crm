import unicodedata


def normalize_name(value: str) -> str:
    return " ".join(value.split())


def _fold(value: str) -> str:
    value = normalize_name(value).lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def name_key(first: str, last: str) -> str:
    return f"{_fold(first)} {_fold(last)}"
