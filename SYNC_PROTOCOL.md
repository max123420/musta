# Synchronization protocol (required production contract)

1. Clinic app appends an event locally in the same transaction as the source change.
2. Worker sends `{event_id, idempotency_key, clinic_id, type, payload, occurred_at}` over TLS with authenticated clinic identity.
3. Central service durably records the idempotency key before processing and returns an acknowledged cursor.
4. Retry only unacknowledged events using exponential backoff; move exhausted events to a dead-letter queue.
5. The server never overwrites protected clinical fields on conflict. It returns `needs_review` with both versions and an audit entry.
6. Operators can view queued, synchronized, failed, blocked, and needs-review states without silently changing clinical content.

The transport worker and central ingest endpoint are intentionally not active in this pilot foundation.
