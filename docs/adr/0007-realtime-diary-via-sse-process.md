# Real-time diary updates via server-sent events from a separate process

Open diaries update within a second when anyone books, moves or checks in a patient at the same Clinic. The outbox worker publishes each diary event to a Redis pub/sub channel, one per Clinic (ADR 0006). A small ASGI process (`realtime`, built on Starlette) holds the long-lived server-sent event (SSE) connections and forwards those events to browsers. It authenticates with the same Redis-backed session cookie as the API, and subscribes only to channels of Clinics in the session's Organization. Events carry identifiers only, no patient data; browsers refetch the diary query to update.

The Flask API stays a plain synchronous WSGI app. Long-lived connections in Flask would need gevent workers, which psycopg 3 does not support cleanly.

## Considered options

- **Polling every few seconds**: simple, but laggy and wasteful across many open diaries.
- **WebSockets**: two-way communication isn't needed; SSE reconnects by itself and is simpler behind Caddy.

## Consequences

- One more process to deploy and monitor.
- The double-booking constraint stays the source of truth; live updates only reduce how often people try to book a taken slot.
