"""identity: Invitations, and the public lookup by token hash

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE invitations (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            email citext NOT NULL,
            full_name text NOT NULL,
            roles staff_role[] NOT NULL,
            clinic_ids uuid[] NOT NULL,
            token_hash char(64) NOT NULL UNIQUE,
            status text NOT NULL DEFAULT 'pending',
            expires_at timestamptz NOT NULL,
            created_by_staff_member_id uuid NOT NULL,
            accepted_staff_member_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            accepted_at timestamptz,
            UNIQUE (organization_id, id),
            FOREIGN KEY (organization_id, created_by_staff_member_id)
                REFERENCES staff_members (organization_id, id),
            FOREIGN KEY (organization_id, accepted_staff_member_id)
                REFERENCES staff_members (organization_id, id) DEFERRABLE INITIALLY DEFERRED,
            CONSTRAINT ck_invitations_status CHECK (status IN ('pending', 'accepted', 'revoked')),
            CONSTRAINT ck_invitations_roles_not_empty CHECK (cardinality(roles) >= 1),
            CONSTRAINT ck_invitations_clinics_not_empty CHECK (cardinality(clinic_ids) >= 1)
        )
        """
    )
    op.execute("CREATE INDEX ix_invitations_organization_id ON invitations (organization_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_invitations_pending_email ON invitations (organization_id, email) "
        "WHERE status = 'pending'"
    )
    op.execute("ALTER TABLE invitations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON invitations "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT ON invitations TO crm_app")
    op.execute("GRANT UPDATE (status, accepted_at, accepted_staff_member_id) ON invitations TO crm_app")

    op.execute(
        """
        CREATE FUNCTION public_invitation(p_token_hash text)
        RETURNS TABLE (id uuid, organization_id uuid, organization_name text, email text,
                       full_name text, status text, expires_at timestamptz)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT i.id, i.organization_id, o.name, i.email::text, i.full_name, i.status, i.expires_at
            FROM invitations i JOIN organizations o ON o.id = i.organization_id
            WHERE i.token_hash = p_token_hash
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public_invitation(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public_invitation(text) TO crm_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION public_invitation(text)")
    op.execute("DROP TABLE invitations")
