"""append-only audit log

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ACTIONS = ("view", "export", "create", "update", "delete", "login", "login_failed", "logout")


def upgrade() -> None:
    actions = ", ".join(f"'{a}'" for a in ACTIONS)
    op.execute(
        f"""
        CREATE TABLE audit_entries (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            staff_member_id uuid,
            account_id uuid REFERENCES accounts (id),
            action text NOT NULL,
            entity_type text NOT NULL,
            entity_id uuid,
            detail jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_audit_entries_action CHECK (action IN ({actions})),
            FOREIGN KEY (organization_id, staff_member_id)
                REFERENCES staff_members (organization_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_audit_entries_organization_id_occurred_at "
        "ON audit_entries (organization_id, occurred_at)"
    )
    op.execute("ALTER TABLE audit_entries ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_entries "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT ON audit_entries TO crm_app")


def downgrade() -> None:
    op.execute("DROP TABLE audit_entries")
