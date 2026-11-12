"""people: patients (tenant table with generated unaccented search text)

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE FUNCTION f_unaccent(text) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT "
        "AS $$ SELECT public.unaccent('public.unaccent', $1) $$"
    )
    op.execute(
        """
        CREATE TABLE patients (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations (id),
            first_name text NOT NULL,
            last_name text NOT NULL,
            date_of_birth date,
            phone_e164 text,
            email citext,
            oib char(11),
            address text,
            notes text,
            preferred_clinic_id uuid,
            preferred_language text NOT NULL DEFAULT 'hr',
            retired_into_patient_id uuid,
            retired_at timestamptz,
            import_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            search_text text GENERATED ALWAYS AS (
                f_unaccent(lower(first_name || ' ' || last_name || ' ' || coalesce(email, '')
                    || ' ' || coalesce(phone_e164, '') || ' ' || coalesce(oib, '')))
            ) STORED,
            UNIQUE (organization_id, id),
            FOREIGN KEY (organization_id, preferred_clinic_id)
                REFERENCES clinics (organization_id, id),
            FOREIGN KEY (organization_id, retired_into_patient_id)
                REFERENCES patients (organization_id, id),
            CONSTRAINT ck_patients_first_name_len CHECK (char_length(first_name) BETWEEN 1 AND 100),
            CONSTRAINT ck_patients_last_name_len CHECK (char_length(last_name) BETWEEN 1 AND 100),
            CONSTRAINT ck_patients_address_len CHECK (char_length(address) <= 300),
            CONSTRAINT ck_patients_notes_len CHECK (char_length(notes) <= 500),
            CONSTRAINT ck_patients_language CHECK (preferred_language IN ('hr', 'en'))
        )
        """
    )
    op.execute("CREATE INDEX ix_patients_organization_id ON patients (organization_id)")
    op.execute("CREATE INDEX ix_patients_search_text_trgm ON patients USING gin (search_text gin_trgm_ops)")
    op.execute(
        "CREATE UNIQUE INDEX uq_patients_org_oib ON patients (organization_id, oib) "
        "WHERE oib IS NOT NULL AND retired_at IS NULL"
    )
    op.execute("ALTER TABLE patients ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON patients "
        "USING (organization_id = app_current_org()) "
        "WITH CHECK (organization_id = app_current_org())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON patients TO crm_app")


def downgrade() -> None:
    op.execute("DROP TABLE patients")
    op.execute("DROP FUNCTION f_unaccent(text)")
