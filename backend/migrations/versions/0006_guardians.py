"""people: contacts and guardian links

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contacts (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            full_name text NOT NULL,
            phone_e164 text,
            email citext,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (organization_id, id),
            CONSTRAINT ck_contacts_full_name_len CHECK (char_length(full_name) BETWEEN 1 AND 200)
        )
        """
    )
    op.execute("CREATE INDEX ix_contacts_organization_id ON contacts (organization_id)")
    op.execute(
        """
        CREATE TABLE guardian_links (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            patient_id uuid NOT NULL,
            guardian_patient_id uuid,
            guardian_contact_id uuid,
            relationship text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (organization_id, patient_id) REFERENCES patients (organization_id, id),
            FOREIGN KEY (organization_id, guardian_patient_id) REFERENCES patients (organization_id, id),
            FOREIGN KEY (organization_id, guardian_contact_id) REFERENCES contacts (organization_id, id),
            CONSTRAINT ck_guardian_links_relationship CHECK (relationship IN ('parent', 'legal_guardian', 'other')),
            CONSTRAINT ck_guardian_links_one_guardian CHECK (
                (guardian_patient_id IS NOT NULL) <> (guardian_contact_id IS NOT NULL)
            ),
            CONSTRAINT ck_guardian_links_not_self CHECK (guardian_patient_id IS DISTINCT FROM patient_id),
            CONSTRAINT uq_guardian_links_patient_guardian UNIQUE (patient_id, guardian_patient_id),
            CONSTRAINT uq_guardian_links_patient_contact UNIQUE (patient_id, guardian_contact_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_guardian_links_organization_id ON guardian_links (organization_id)")
    op.execute("CREATE INDEX ix_guardian_links_guardian_patient ON guardian_links (guardian_patient_id)")
    op.execute("CREATE INDEX ix_guardian_links_guardian_contact ON guardian_links (guardian_contact_id)")
    for table in ("contacts", "guardian_links"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (organization_id = app_current_org()) "
            "WITH CHECK (organization_id = app_current_org())"
        )
    op.execute("GRANT SELECT, INSERT, UPDATE ON contacts TO crm_app")
    op.execute("GRANT SELECT, INSERT, DELETE ON guardian_links TO crm_app")


def downgrade() -> None:
    op.execute("DROP TABLE guardian_links")
    op.execute("DROP TABLE contacts")
