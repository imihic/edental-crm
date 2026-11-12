from sqlalchemy import text


def _tenant_tables(conn) -> list[str]:
    return list(
        conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'organization_id' "
                "AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') "
                "ORDER BY table_name"
            )
        ).scalars()
    )


def test_every_tenant_table_has_rls_and_policy(owner_engine):
    with owner_engine.connect() as conn:
        tables = _tenant_tables(conn)
        assert "audit_entries" in tables and "staff_members" in tables
        for table in tables:
            rls = conn.execute(
                text("SELECT relrowsecurity FROM pg_class WHERE oid = CAST(:t AS regclass)"),
                {"t": f"public.{table}"},
            ).scalar_one()
            assert rls, f"{table}: row level security is not enabled"
            policy = conn.execute(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname = 'public' "
                    "AND tablename = :t AND policyname = 'tenant_isolation'"
                ),
                {"t": table},
            ).scalar_one()
            assert policy == 1, f"{table}: missing tenant_isolation policy"


def test_organizations_and_accounts_have_rls(owner_engine):
    with owner_engine.connect() as conn:
        for table in ("organizations", "accounts"):
            assert conn.execute(
                text("SELECT relrowsecurity FROM pg_class WHERE oid = CAST(:t AS regclass)"),
                {"t": f"public.{table}"},
            ).scalar_one(), f"{table}: row level security is not enabled"


def test_audit_entries_not_updatable_by_app_role(owner_engine):
    with owner_engine.connect() as conn:
        for priv in ("UPDATE", "DELETE"):
            assert not conn.execute(
                text("SELECT has_table_privilege('crm_app', 'public.audit_entries', :p)"),
                {"p": priv},
            ).scalar_one()
        assert conn.execute(
            text("SELECT has_table_privilege('crm_app', 'public.audit_entries', 'INSERT')")
        ).scalar_one()
