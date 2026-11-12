"""accounts, staff members with roles, staff clinics, sign-in lookups

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE TYPE staff_role AS ENUM ('receptionist', 'dentist', 'clinic_manager')")

    op.execute(
        """
        CREATE TABLE accounts (
            id uuid PRIMARY KEY,
            email citext NOT NULL UNIQUE,
            password_hash text NOT NULL,
            totp_secret_encrypted text,
            totp_enabled boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE staff_members (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            account_id uuid NOT NULL REFERENCES accounts (id),
            full_name text NOT NULL,
            roles staff_role[] NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (account_id, organization_id),
            UNIQUE (organization_id, id),
            CONSTRAINT ck_staff_members_roles_not_empty CHECK (cardinality(roles) >= 1)
        )
        """
    )
    op.execute("CREATE INDEX ix_staff_members_organization_id ON staff_members (organization_id)")
    op.execute("ALTER TABLE staff_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON staff_members "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON staff_members TO crm_app")
    op.execute("GRANT UPDATE (full_name, roles, is_active) ON staff_members TO crm_app")

    op.execute("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY")
    visible = (
        "id = app_current_account() OR EXISTS (SELECT 1 FROM staff_members sm "
        "WHERE sm.account_id = accounts.id AND sm.organization_id = app_current_org())"
    )
    op.execute(f"CREATE POLICY accounts_visible ON accounts FOR SELECT USING ({visible})")
    op.execute(
        "CREATE POLICY accounts_update ON accounts FOR UPDATE "
        "USING (id = app_current_account()) WITH CHECK (id = app_current_account())"
    )
    op.execute("CREATE POLICY accounts_insert ON accounts FOR INSERT WITH CHECK (true)")
    op.execute("GRANT SELECT, INSERT, UPDATE ON accounts TO crm_app")

    op.execute(
        """
        CREATE TABLE staff_clinics (
            organization_id uuid NOT NULL REFERENCES organizations (id),
            staff_member_id uuid NOT NULL,
            clinic_id uuid NOT NULL,
            PRIMARY KEY (staff_member_id, clinic_id),
            FOREIGN KEY (organization_id, staff_member_id)
                REFERENCES staff_members (organization_id, id),
            FOREIGN KEY (organization_id, clinic_id)
                REFERENCES clinics (organization_id, id)
        )
        """
    )
    op.execute("CREATE INDEX ix_staff_clinics_organization_id ON staff_clinics (organization_id)")
    op.execute("CREATE INDEX ix_staff_clinics_clinic_id ON staff_clinics (clinic_id)")
    op.execute("ALTER TABLE staff_clinics ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON staff_clinics "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON staff_clinics TO crm_app")

    op.execute(
        """
        CREATE FUNCTION auth_find_account(p_email text)
        RETURNS TABLE (id uuid, password_hash text, totp_enabled boolean,
                       totp_secret_encrypted text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT a.id, a.password_hash, a.totp_enabled, a.totp_secret_encrypted
            FROM accounts a WHERE a.email = p_email::citext
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION auth_list_memberships(p_account_id uuid)
        RETURNS TABLE (staff_member_id uuid, organization_id uuid, organization_name text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT sm.id, o.id, o.name
            FROM staff_members sm JOIN organizations o ON o.id = sm.organization_id
            WHERE sm.account_id = p_account_id AND sm.is_active
            ORDER BY o.name, sm.id
        $$
        """
    )
    for fn in ("auth_find_account(text)", "auth_list_memberships(uuid)"):
        op.execute(f"REVOKE ALL ON FUNCTION {fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn} TO crm_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION auth_list_memberships(uuid)")
    op.execute("DROP FUNCTION auth_find_account(text)")
    op.execute("DROP TABLE staff_clinics")
    op.execute("DROP POLICY accounts_visible ON accounts")
    op.execute("DROP POLICY accounts_update ON accounts")
    op.execute("DROP TABLE staff_members")
    op.execute("DROP TABLE accounts")
    op.execute("DROP TYPE staff_role")
