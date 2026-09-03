# B01 implementation guardrails

- Public login identity is email; the inherited `AbstractUser.username` remains an internal implementation field and is never accepted/returned by customer APIs.
- `apps.accounts.backends.EmailAuthenticationBackend` performs email lookup, Django password checks, active-user checks and a dummy password hash for unknown emails.
- Browser auth uses Django database sessions and DRF `SessionAuthentication`.
- Registration, login and logout are explicitly protected by Django CSRF processing; middleware CSRF failures are normalized to RFC 9457-style JSON through `CSRF_FAILURE_VIEW`.
- Profile PATCH cannot silently change email. A future email-change flow must verify the new login identifier.
- Address ownership is derived from the authenticated request; public clients cannot assign owners.
- PostgreSQL transaction + per-user row lock + conditional unique constraint protect the one-default-address invariant.
- DRF throttling is only basic abuse/service-overuse control and is not treated as brute-force or DoS protection.
