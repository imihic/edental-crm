"""people: Patient search text no longer contains the OIB

The OIB is only found through the audited exact lookup / reveal, never by substring search.

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _regenerate(expression: str) -> None:
    op.execute("DROP INDEX ix_patients_search_text_trgm")
    op.execute("ALTER TABLE patients DROP COLUMN search_text")
    op.execute(f"ALTER TABLE patients ADD COLUMN search_text text GENERATED ALWAYS AS ({expression}) STORED")
    op.execute("CREATE INDEX ix_patients_search_text_trgm ON patients USING gin (search_text gin_trgm_ops)")


def upgrade() -> None:
    _regenerate(
        "f_unaccent(lower(first_name || ' ' || last_name || ' ' || coalesce(email, '')"
        " || ' ' || coalesce(phone_e164, '')))"
    )


def downgrade() -> None:
    _regenerate(
        "f_unaccent(lower(first_name || ' ' || last_name || ' ' || coalesce(email, '')"
        " || ' ' || coalesce(phone_e164, '') || ' ' || coalesce(oib, '')))"
    )
