"""identity tenancy: tenant-context functions, organizations, clinics

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE FUNCTION app_current_org() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.current_org', true), '')::uuid $$"
    )
    op.execute(
        "CREATE FUNCTION app_current_account() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.current_account', true), '')::uuid $$"
    )

    op.execute(
        """
        CREATE TABLE organizations (
            id uuid PRIMARY KEY,
            name text NOT NULL,
            timezone text NOT NULL DEFAULT 'Europe/Zagreb',
            currency text NOT NULL DEFAULT 'EUR',
            locale text NOT NULL DEFAULT 'hr',
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON organizations "
        "USING (id = app_current_org()) WITH CHECK (id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON organizations TO crm_app")

    op.execute(
        """
        CREATE TABLE clinics (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (organization_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_clinics_organization_id ON clinics (organization_id)")
    op.execute("ALTER TABLE clinics ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON clinics "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON clinics TO crm_app")


def downgrade() -> None:
    op.execute("DROP TABLE clinics")
    op.execute("DROP TABLE organizations")
    op.execute("DROP FUNCTION app_current_account()")
    op.execute("DROP FUNCTION app_current_org()")
