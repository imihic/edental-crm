from testing import fake_email, fake_password

import pyotp

from app.identity.core.passwords import DUMMY_HASH, hash_password, verify_password
from app.identity.core.permissions import has_any_role, requires_totp
from app.identity.core.totp import (
    decrypt_secret,
    encrypt_secret,
    new_secret,
    matched_step,
    provisioning_uri,
)
from app.identity.models import Role
from app.platform.config import TestConfig

KEY = TestConfig.TOTP_ENCRYPTION_KEY


def test_requires_totp_for_any_set_containing_manager():
    assert requires_totp([Role.DENTIST, Role.CLINIC_MANAGER]) and not requires_totp([Role.DENTIST])


def test_has_any_role():
    assert has_any_role([Role.DENTIST], Role.DENTIST, Role.CLINIC_MANAGER)
    assert not has_any_role([Role.RECEPTIONIST], Role.DENTIST)


def test_totp_secret_round_trips_and_ciphertext_differs():
    secret = new_secret()
    token = encrypt_secret(secret, KEY)
    assert token != secret and secret not in token
    assert decrypt_secret(token, KEY) == secret


def test_matched_step_returns_the_step_of_the_code():
    secret = new_secret()
    totp = pyotp.TOTP(secret)
    at = 1_700_000_000.0
    step = int(at) // 30
    for offset in (-1, 0, 1):
        assert matched_step(secret, totp.generate_otp(step + offset), at) == step + offset
    assert matched_step(secret, totp.generate_otp(step - 2), at) is None
    assert matched_step(secret, totp.generate_otp(step + 2), at) is None
    valid = {totp.generate_otp(step + d) for d in (-1, 0, 1)}
    wrong = next(c for c in ("000000", "111111", "222222") if c not in valid)
    assert matched_step(secret, wrong, at) is None
    assert matched_step(secret, "not-a-code", at) is None
    assert matched_step(secret, totp.now()) is not None


def test_provisioning_uri_has_issuer():
    uri = provisioning_uri(new_secret(), fake_email('testa', 'clinic.example.test'))
    assert uri.startswith("otpauth://totp/") and "issuer=Dental+CRM" in uri.replace("%20", "+")


def test_password_hash_verifies():
    h = hash_password(fake_password('account'))
    assert verify_password(h, fake_password('account'))
    assert not verify_password(h, "wrong")
    assert not verify_password(DUMMY_HASH, "anything")
    assert not verify_password("garbage", "x")
