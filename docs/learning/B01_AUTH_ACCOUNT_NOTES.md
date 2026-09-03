# B01 — Python / Django Auth Learning Notes

## What this phase teaches

B01 keeps authentication on Django's built-in primitives instead of inventing a token system.

- `SessionAuthentication` means the browser sends the Django session cookie and the server resolves `request.user`.
- CSRF is a separate protection for unsafe cookie-authenticated requests. Authentication and CSRF solve different problems.
- Login and registration are explicitly CSRF-protected because anonymous login requests are not protected merely by adding DRF `SessionAuthentication`.
- `django.contrib.auth.login()` rotates the session key when authentication succeeds.
- `update_session_auth_hash()` keeps the current user logged in after a legitimate password change while rotating the session key/hash.
- Password quality comes from Django's configured password validators rather than ad-hoc regex rules.

## Public email, internal username

The B00 user model already inherits from `AbstractUser`, whose migration includes a unique `username`. B01 does not delete that field merely to make the database look cleaner.

The public API accepts email as the login identity. Registration creates an opaque random internal username and never returns it. The email authentication backend resolves the public email to the internal user and uses Django's password checking and active-user rules.

For a missing email the backend still performs a dummy password hash. This follows the same timing-hardening idea used by Django's default model backend so a missing account is not an obvious fast path.

## Address ownership

The address serializer uses `CurrentUserDefault()` through a hidden `user` field. A client cannot choose a `user_id`. The views also filter every address queryset by `request.user`, so another customer's object id resolves as not found.

When an address becomes default, the code takes a PostgreSQL row lock on the owning user inside a transaction, clears the old default and writes the new state. A conditional unique constraint remains the database-level final defense: only one row with `is_default=true` is allowed for each user.

## Throttling boundary

DRF scoped throttling is used for basic service-overuse control on registration/login. DRF explicitly warns that its built-in throttling is not a brute-force or denial-of-service security boundary because cache operations are non-atomic and client IP identity can be spoofed or affected by proxy/NAT topology.

Later deployment phases must supply trusted proxy/edge rate controls. B01 does not pretend an application cache throttle is equivalent to perimeter security.

## What is intentionally deferred

- email verification delivery;
- password-reset email delivery;
- phone verification/OTP;
- CORS and cross-subdomain cookie topology;
- shipping eligibility and delivery zones;
- payment/order identity coupling.

Those require real provider/integration/deployment decisions instead of fake B01 implementations.
