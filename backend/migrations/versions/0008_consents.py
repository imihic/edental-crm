"""people: append-only consents

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE guardian_links ADD CONSTRAINT uq_guardian_links_org_id UNIQUE (organization_id, id)"
    )
    op.execute(
        """
        CREATE TABLE consents (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            patient_id uuid,
            lead_id uuid,
            purpose text NOT NULL,
            granted boolean NOT NULL,
            source text NOT NULL,
            given_by_guardian_link_id uuid,
            carried_from_consent_id uuid,
            recorded_by_staff_member_id uuid,
            recorded_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (organization_id, id),
            FOREIGN KEY (organization_id, patient_id) REFERENCES patients (organization_id, id),
            FOREIGN KEY (organization_id, lead_id) REFERENCES leads (organization_id, id),
            FOREIGN KEY (organization_id, given_by_guardian_link_id)
                REFERENCES guardian_links (organization_id, id),
            FOREIGN KEY (organization_id, carried_from_consent_id) REFERENCES consents (organization_id, id),
            FOREIGN KEY (organization_id, recorded_by_staff_member_id)
                REFERENCES staff_members (organization_id, id),
            CONSTRAINT ck_consents_one_subject CHECK ((patient_id IS NOT NULL) <> (lead_id IS NOT NULL)),
            CONSTRAINT ck_consents_purpose CHECK (purpose IN ('marketing')),
            CONSTRAINT ck_consents_source CHECK (
                source IN ('form', 'paper', 'verbal', 'enquiry_form', 'conversion', 'merge')
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_consents_organization_id ON consents (organization_id)")
    op.execute("CREATE INDEX ix_consents_patient ON consents (organization_id, patient_id, recorded_at)")
    op.execute("CREATE INDEX ix_consents_lead ON consents (organization_id, lead_id, recorded_at)")
    op.execute("ALTER TABLE consents ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON consents "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT ON consents TO crm_app")


def downgrade() -> None:
    op.execute("DROP TABLE consents")
    op.execute("ALTER TABLE guardian_links DROP CONSTRAINT uq_guardian_links_org_id")
