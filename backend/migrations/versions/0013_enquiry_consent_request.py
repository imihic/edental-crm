"""people: an Enquiry records that marketing Consent was requested

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE enquiries ADD COLUMN marketing_consent_requested boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE enquiries DROP COLUMN marketing_consent_requested")
