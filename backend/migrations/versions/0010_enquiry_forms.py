"""people: public Enquiry Form per Clinic

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE enquiry_forms (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            clinic_id uuid NOT NULL UNIQUE,
            key text NOT NULL UNIQUE,
            enabled boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            rotated_at timestamptz,
            UNIQUE (organization_id, id),
            FOREIGN KEY (organization_id, clinic_id) REFERENCES clinics (organization_id, id),
            CONSTRAINT ck_enquiry_forms_key CHECK (key ~ '^[A-Za-z0-9_-]{20,64}$')
        )
        """
    )
    op.execute("CREATE INDEX ix_enquiry_forms_organization_id ON enquiry_forms (organization_id)")
    op.execute("ALTER TABLE enquiry_forms ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON enquiry_forms "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON enquiry_forms TO crm_app")

    op.execute(
        """
        CREATE FUNCTION public_enquiry_form(p_key text)
        RETURNS TABLE (organization_id uuid, clinic_id uuid, clinic_name text,
                       organization_name text, locale text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
            SELECT f.organization_id, f.clinic_id, c.name, o.name, o.locale
            FROM enquiry_forms f
            JOIN clinics c ON c.organization_id = f.organization_id AND c.id = f.clinic_id
            JOIN organizations o ON o.id = f.organization_id
            WHERE f.key = p_key AND f.enabled
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public_enquiry_form(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public_enquiry_form(text) TO crm_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION public_enquiry_form(text)")
    op.execute("DROP TABLE enquiry_forms")
