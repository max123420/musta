# Database schema

`users` and `sessions` provide local identity and expiry. `patients` holds demographic and consent fields; `encounters` separates draft from signed clinical records. `invoices` and `payments` maintain verified payment totals. `audit_events` records security and sensitive business actions. `outbox` is append-only and stores event payloads and idempotency keys for later synchronization.

This pilot SQLite schema is a local-deployment model. A central production deployment requires PostgreSQL migrations, `organization_id` on every tenant-owned record, foreign-key/row-level enforcement, key rotation, and retention/archival rules.
