# Domain events with a transactional outbox; a scanner for timed work

Modules react to each other through domain events, such as `AppointmentCompleted` and `LeadConverted`, rather than by calling each other directly.

- **Data consequences** (setting the next Recall) run as in-process handlers inside the same database transaction.
- **External side effects** (sending a message, pushing a live diary update) are recorded in an `outbox` table in that same transaction. A worker processes the outbox afterwards.

A rolled-back booking therefore never sends a reminder, and a crash or Redis outage never loses one.

Timed work (Appointment Reminders, due Recalls, Treatment Plan follow-ups) is not enqueued as delayed jobs. A scanner runs every minute, asks the database what is due, and performs each item once. A unique idempotency key in the database, such as `(appointment_id, reminder_kind)`, prevents duplicates. Rescheduling and cancelling therefore need no job bookkeeping.

## Considered options

- **Direct calls between modules**: couples modules in both directions and puts external I/O inside request transactions.
- **Delayed jobs per message**: a rescheduled or cancelled Appointment would leave stale jobs to hunt down.
- **Event sourcing**: rejected. Immutable event logs conflict with GDPR erasure (ADR 0003) unless every Patient's data is encrypted with its own key ("crypto-shredding"), which is a large cost for no product benefit. The Audit Log already covers the audit trail.

## Consequences

- Outbox processing and scanners must be idempotent and must set the Organization context per item (ADR 0001).
- Delivery is at-least-once: an external send can repeat after a crash, so the idempotency check happens before each send.
