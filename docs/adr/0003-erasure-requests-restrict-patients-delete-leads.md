# Erasure requests restrict Patients and delete Leads

When someone asks to be forgotten, a Lead who never became a Patient is deleted outright. A Patient is instead restricted: all contact stops, marketing consents are withdrawn, and the record is hidden from normal use. It is anonymised only when the Organization's retention period has ended.

Deleting Patients on request would conflict with the clinic's legal duty to keep health-related records (appointment history included) for a number of years. Ignoring the request would breach GDPR. Restriction plus scheduled anonymisation satisfies both.

## Consequences

- Every list, search, report and message job must exclude restricted Patients.
- A scheduled job anonymises restricted Patients whose retention period has ended; anonymisation is irreversible.
- The retention period is configured per Organization, and its default must come from confirmed Croatian law, not a guess.
