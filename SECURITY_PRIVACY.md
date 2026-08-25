# Security and privacy status

Implemented pilot controls: PBKDF2-HMAC-SHA256 password hashing, 15-minute lockout after repeated failures, expiring HTTP-only session cookie, role checks on protected endpoints, parameterized SQLite queries, input length validation, signed-record immutability, and security audit records. Demo data is synthetic only.

Not production-ready: cookie `Secure` must be enabled behind HTTPS; CSRF protection, MFA, password-reset verification, tenant isolation, encrypted-at-rest database management, secrets vault, structured redacted logging, independent penetration test, restore drills, legal/privacy review, and clinical governance must be completed. Never place real patient data in the demo build or logs.
