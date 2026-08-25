# Architecture

Clinic Edition is the primary clinical write system. It stores operational data in local SQLite for this pilot foundation and writes each eligible synchronization event to an append-only outbox with a UUID idempotency key. The Central Edition is deployed separately with its own data store. A production sync worker must use mTLS or short-lived service credentials, exponential backoff, a pull cursor, dead-letter handling, and a human conflict queue.

Clinical records use a `draft → signed` transition. A signed encounter cannot be edited by this API; an addendum endpoint remains a required next implementation. Conflicts for diagnoses, allergies, prescriptions, laboratory results, and radiology reports must never use last-write-wins.

Production evolution: FastAPI services → PostgreSQL per deployment → background worker → object storage for encrypted attachments/backups → reverse proxy/TLS → observability. Tenant identity must be carried by every business record and enforced in every query before central multi-facility deployment.
