"""people: patient imports (CSV preview and commit)

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE patient_imports (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            filename text NOT NULL,
            status text NOT NULL DEFAULT 'previewed',
            rows jsonb NOT NULL,
            created_by_staff_member_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            committed_at timestamptz,
            counts jsonb NOT NULL DEFAULT '{}'::jsonb,
            UNIQUE (organization_id, id),
            FOREIGN KEY (organization_id, created_by_staff_member_id)
                REFERENCES staff_members (organization_id, id),
            CONSTRAINT ck_patient_imports_status CHECK (status IN ('previewed', 'committed', 'expired'))
        )
        """
    )
    op.execute("CREATE INDEX ix_patient_imports_organization_id ON patient_imports (organization_id, created_at)")
    op.execute("ALTER TABLE patient_imports ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON patient_imports "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON patient_imports TO crm_app")
    op.execute(
        "ALTER TABLE patients ADD CONSTRAINT fk_patients_import "
        "FOREIGN KEY (organization_id, import_id) REFERENCES patient_imports (organization_id, id)"
    )
    op.execute("CREATE INDEX ix_patients_import ON patients (organization_id, import_id) WHERE import_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX ix_patients_import")
    op.execute("ALTER TABLE patients DROP CONSTRAINT fk_patients_import")
    op.execute("DROP TABLE patient_imports")
