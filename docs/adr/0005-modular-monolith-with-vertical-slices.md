# Modular monolith with vertical slices and a functional core

The backend is one Flask application split into modules by domain area: `identity`, `people`, `scheduling`, `engagement`, `messaging`, `compliance` and `reporting`, plus a shared `platform` package for infrastructure. Each module exposes a small public interface from its package root. Other modules may import only that root (and `platform`), never a module's internals, and an import-linter contract enforces this in the test suite.

Inside a module, code is organised by use case. Each slice (`book_appointment/`, `login/`) holds its route, schemas, handler and tests. Rules with real logic (slot finding, recall dates, state machines, follow-up timing) live in the module's `core/` as pure functions with no I/O. Handlers use SQLAlchemy directly. Ports and adapters exist only where an implementation genuinely varies: the message provider, the clock, and importers.

## Considered options

- **Microservices**: rejected for now. They would turn single-transaction workflows into sagas, multiply tenant isolation and GDPR erasure across services, and add operations work for a one-person team. A module with enforced boundaries can be extracted later.
- **Full hexagonal with repository ports and separate domain entities**: rejected. Tenant isolation, double-booking prevention and audit immutability are Postgres behaviour, so in-memory repository fakes would pass tests the real system fails. A repository with one adapter is ceremony.
- **Classic layers (routes, services, repositories)**: rejected. Each feature gets spread across layers, and the repository layer mostly passes calls straight through.

## Consequences

- Behaviour is tested through each slice's HTTP interface or module function, against real Postgres. Pure core functions get fast, exhaustive unit tests.
- Commands that change state are explicit endpoints (`POST /appointments/{id}/complete`), each backed by a state machine in `core/`. Invalid transitions return 409 `invalid_transition`.
- Read-heavy screens (diary, dashboard) use dedicated query slices with tuned SQL rather than the command path (light CQRS). There is no separate read database.
