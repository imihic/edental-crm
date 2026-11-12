"""people: leads and enquiries

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE leads (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            full_name text NOT NULL,
            phone_e164 text,
            email citext,
            clinic_id uuid NOT NULL,
            stage text NOT NULL DEFAULT 'new',
            lost_reason text,
            lost_note text,
            converted_patient_id uuid,
            retired_into_patient_id uuid,
            retired_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            search_text text GENERATED ALWAYS AS (
                f_unaccent(lower(full_name || ' ' || coalesce(email, '') || ' ' || coalesce(phone_e164, '')))
            ) STORED,
            UNIQUE (organization_id, id),
            FOREIGN KEY (organization_id, clinic_id) REFERENCES clinics (organization_id, id),
            FOREIGN KEY (organization_id, converted_patient_id) REFERENCES patients (organization_id, id),
            FOREIGN KEY (organization_id, retired_into_patient_id) REFERENCES patients (organization_id, id),
            CONSTRAINT ck_leads_full_name_len CHECK (char_length(full_name) BETWEEN 1 AND 200),
            CONSTRAINT ck_leads_stage CHECK (
                stage IN ('new', 'contacted', 'consultation_booked', 'converted', 'lost')
            ),
            CONSTRAINT ck_leads_lost_reason CHECK (
                lost_reason IS NULL OR lost_reason IN
                    ('price', 'distance', 'chose_other_clinic', 'no_response', 'not_needed', 'other')
            ),
            CONSTRAINT ck_leads_lost_note_len CHECK (char_length(lost_note) <= 500),
            CONSTRAINT ck_leads_lost_iff_reason CHECK ((stage = 'lost') = (lost_reason IS NOT NULL)),
            CONSTRAINT ck_leads_converted_iff_patient CHECK (
                (stage = 'converted') = (converted_patient_id IS NOT NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_leads_organization_id ON leads (organization_id)")
    op.execute("CREATE INDEX ix_leads_search_text_trgm ON leads USING gin (search_text gin_trgm_ops)")
    op.execute("CREATE INDEX ix_leads_org_email ON leads (organization_id, email) WHERE email IS NOT NULL")
    op.execute(
        """
        CREATE TABLE enquiries (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            lead_id uuid,
            patient_id uuid,
            clinic_id uuid NOT NULL,
            source text NOT NULL,
            message text NOT NULL,
            preferred_contact_time text,
            received_at timestamptz NOT NULL DEFAULT now(),
            created_by_staff_member_id uuid,
            FOREIGN KEY (organization_id, lead_id) REFERENCES leads (organization_id, id),
            FOREIGN KEY (organization_id, patient_id) REFERENCES patients (organization_id, id),
            FOREIGN KEY (organization_id, clinic_id) REFERENCES clinics (organization_id, id),
            FOREIGN KEY (organization_id, created_by_staff_member_id)
                REFERENCES staff_members (organization_id, id),
            CONSTRAINT ck_enquiries_has_subject CHECK (lead_id IS NOT NULL OR patient_id IS NOT NULL),
            CONSTRAINT ck_enquiries_source CHECK (
                source IN ('website_form', 'phone', 'walk_in', 'email', 'other')
            ),
            CONSTRAINT ck_enquiries_message_len CHECK (char_length(message) <= 2000),
            CONSTRAINT ck_enquiries_contact_time_len CHECK (char_length(preferred_contact_time) <= 100)
        )
        """
    )
    op.execute("CREATE INDEX ix_enquiries_organization_id ON enquiries (organization_id)")
    op.execute("CREATE INDEX ix_enquiries_lead ON enquiries (lead_id, received_at)")
    op.execute("CREATE INDEX ix_enquiries_patient ON enquiries (patient_id, received_at)")
    for table in ("leads", "enquiries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            "USING (organization_id = app_current_org()) "
            "WITH CHECK (organization_id = app_current_org())"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO crm_app")


def downgrade() -> None:
    op.execute("DROP TABLE enquiries")
    op.execute("DROP TABLE leads")
