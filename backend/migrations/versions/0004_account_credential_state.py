"""accounts: last accepted TOTP time step (replay guard) and credentials change time (session revocation)

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE accounts ADD COLUMN totp_last_step bigint")
    op.execute("ALTER TABLE accounts ADD COLUMN credentials_changed_at timestamptz NOT NULL DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE accounts DROP COLUMN credentials_changed_at")
    op.execute("ALTER TABLE accounts DROP COLUMN totp_last_step")
