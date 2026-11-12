def is_valid_oib(value: str) -> bool:
    if len(value) != 11 or not (value.isascii() and value.isdigit()):
        return False
    a = 10
    for ch in value[:10]:
        a = (a + int(ch)) % 10
        if a == 0:
            a = 10
        a = (a * 2) % 11
    check = 11 - a
    if check == 10:
        check = 0
    return check == int(value[10])


def mask_oib(value: str) -> str:
    return "*******" + value[-4:]
