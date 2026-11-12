"""people: end guardian links and track Contact promotion

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_GUARDIAN_KEYS = (
    ("uq_guardian_links_patient_guardian", "guardian_patient_id"),
    ("uq_guardian_links_patient_contact", "guardian_contact_id"),
)


def upgrade() -> None:
    op.execute("ALTER TABLE guardian_links ADD COLUMN ended_at timestamptz")
    for name, column in _GUARDIAN_KEYS:
        op.execute(f"ALTER TABLE guardian_links DROP CONSTRAINT {name}")
        op.execute(f"CREATE UNIQUE INDEX {name} ON guardian_links (patient_id, {column}) WHERE ended_at IS NULL")
    op.execute("GRANT UPDATE (ended_at) ON guardian_links TO crm_app")
    op.execute(
        """
        ALTER TABLE contacts ADD COLUMN promoted_to_patient_id uuid,
            ADD CONSTRAINT fk_contacts_promoted_patient FOREIGN KEY (organization_id, promoted_to_patient_id)
                REFERENCES patients (organization_id, id)
        """
    )


def downgrade() -> None:
    op.execute("LOCK TABLE guardian_links IN ACCESS EXCLUSIVE MODE")
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM guardian_links WHERE ended_at IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while ended guardian links exist';
            END IF;
        END $$
        """
    )
    for name, column in _GUARDIAN_KEYS:
        op.execute(f"DROP INDEX {name}")
        op.execute(f"ALTER TABLE guardian_links ADD CONSTRAINT {name} UNIQUE (patient_id, {column})")
    op.execute("REVOKE UPDATE (ended_at) ON guardian_links FROM crm_app")
    op.execute("ALTER TABLE guardian_links DROP COLUMN ended_at")
    op.execute("ALTER TABLE contacts DROP COLUMN promoted_to_patient_id")
