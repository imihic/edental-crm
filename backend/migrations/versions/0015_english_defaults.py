"""Default new organizations and patients to English.

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("organizations", "locale", server_default="en")
    op.alter_column("patients", "preferred_language", server_default="en")


def downgrade() -> None:
    op.alter_column("patients", "preferred_language", server_default="hr")
    op.alter_column("organizations", "locale", server_default="hr")
