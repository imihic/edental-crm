from collections.abc import Iterable

from app.identity.core.roles import Role


def has_any_role(roles: Iterable[Role], *required: Role) -> bool:
    return bool(set(roles) & set(required))


def requires_totp(roles: Iterable[Role]) -> bool:
    return Role.CLINIC_MANAGER in set(roles)
