from testing import fake_email

import pytest
from sqlalchemy import text


@pytest.fixture
def manager_in(client, login, csrf, make_org, make_account, make_staff, make_clinic):
    import pyotp

    from app.identity import Role

    secret = pyotp.random_base32()
    org = make_org("Smile")
    centar = make_clinic(org, "Centar")
    zapad = make_clinic(org, "Zapad")
    staff = make_staff(
        org, make_account(fake_email('mgr', 'clinic.example.test'), totp_secret=secret), roles=(Role.CLINIC_MANAGER,), clinics=(centar,)
    )
    login(client, fake_email('mgr', 'clinic.example.test'), totp_secret=secret)
    staff.clinics_by_name = {"Centar": centar, "Zapad": zapad}
    return org, staff, csrf(client)


@pytest.fixture
def db_rows(owner_engine):
    def _rows(sql: str, **params):
        with owner_engine.connect() as conn:
            return conn.execute(text(sql), params).all()

    return _rows
