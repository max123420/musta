# API documentation

Interactive OpenAPI documentation is available at `/api/docs` while the service is running.

Key endpoints: `POST /setup`, `POST /auth/login`, `POST /auth/logout`, `GET|POST /patients`, `POST /encounters`, `POST /encounters/{id}/sign`, `POST /invoices/{id}/payments`, and `GET /sync/status`. Login sets an HTTP-only session cookie. All endpoints except setup, login, and the static landing page require it.
