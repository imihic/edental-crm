# Shared database with row-level security for tenant isolation

All Organizations share one PostgreSQL database, and every tenant-owned table carries an `organization_id`. Postgres Row-Level Security policies filter rows by the current Organization, which is set per request from the authenticated Staff Member, so a missing filter in application code cannot expose another Organization's patients.

We chose this over a schema or database per tenant because it keeps migrations, connection pooling and reporting simple for a small team. Because the data is health data under GDPR, we accepted the extra complexity of RLS policies and a per-request session variable instead of trusting ORM filters alone.

## Consequences

- The Flask app must connect as a non-superuser role without `BYPASSRLS`, and set the Organization on each connection or transaction before any query.
- Background workers (message sending, imports) must set the Organization context explicitly too.
- Moving one large Organization to its own database later is possible but would be a deliberate migration.
