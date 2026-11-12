# The CRM owns the appointment book but not clinical or billing records

The product runs each Clinic's appointment book itself, instead of mirroring a separate practice management system, because reminders, recalls and treatment follow-up are only reliable when the CRM knows every booking without double entry. Clinical charting, X-rays, invoicing and insurance are explicitly out of scope: they are large, heavily regulated, and would turn a relationship tool into a full practice management system.

## Considered options

- **Mirror the PMS diary by import**: rejected; data is stale between imports and forces clinics to keep a PMS.
- **Full practice management**: rejected for now; scope and regulatory burden far exceed a first product.

## Consequences

- Scheduling (availability, appointment types, conflicts) is core domain, not an integration.
- A Clinic that keeps its own PMS may end up with two diaries; PMS import is a convenience, not a sync.
