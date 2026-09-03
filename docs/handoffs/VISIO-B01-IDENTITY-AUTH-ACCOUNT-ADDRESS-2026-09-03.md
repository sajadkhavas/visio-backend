# VISIO B01 — Identity / Authentication / Account / Address Handoff

Date: 2026-09-03

## Status

`B01_CLOSURE_CANDIDATE`

B01 becomes `COMPLETED / MERGED / CLOSED` only after this documentation head is green, the B01 PR is merged with its expected head SHA, and the post-merge Backend Quality Gate on `main` is green.

## Immutable phase coordinates

- Backend repository: `sajadkhavas/visio-backend`
- Branch: `phase/visio-b01-identity-auth-account-address`
- START_SHA: `4b118845cdbdf8159c5ef5e97252a7a9719588f6`
- Implementation END_SHA: `2bd278034af122bb3c3a485160792fd5f0f1d434`
- Exact implementation gate: Backend Quality Gate #53 / run `33773094652` — PASS
- PostgreSQL test result: `24 passed`
- Final report: `docs/release/B01_FINAL_REPORT.md`
- Architecture decisions: `docs/architecture/B01_IDENTITY_AUTH_ACCOUNT_ADDRESS_DECISIONS.md`
- Implementation notes: `docs/architecture/B01_IMPLEMENTATION_NOTES.md`
- Python learning notes: `docs/learning/B01_AUTH_ACCOUNT_NOTES.md`

## Accepted frozen contracts

### Identity

- Email is the public customer sign-in identifier.
- Email is normalized before authentication/creation.
- Public account payloads never expose Django's inherited `username` field.
- Internal `username` stays opaque to preserve the accepted B00 `AbstractUser` lineage.
- Ordinary profile PATCH cannot change email.

### Browser authentication

- Django DB-backed session cookie is browser auth authority.
- DRF `SessionAuthentication` is the API session adapter.
- Registration/login/logout are explicitly CSRF-protected.
- Browser clients obtain CSRF state from `/api/v1/auth/csrf/` before unsafe anonymous auth requests.
- Password changes preserve the authenticated session with Django's session-auth-hash rotation behavior.
- Unknown-email and wrong-password login responses remain generic.

### Abuse-control boundary

- `ScopedRateThrottle` is active on registration and login.
- B01 application throttle rates are basic abuse controls only.
- They are not accepted as sole brute-force, bot, or DoS protection; network/edge controls belong to later deployment hardening.

### Account

- `/api/v1/account/me/` is authenticated account authority.
- Current public account fields: `id`, `email`, `first_name`, `last_name`, `date_joined`.
- Email-change verification is a future dedicated workflow and must not be smuggled into generic profile update.

### Address

- Address ownership is server-derived from the authenticated user.
- List/detail access is user-scoped at queryset level.
- At most one default address per user is enforced in PostgreSQL and maintained transactionally.
- B01 address data is an address-book contract only.
- B05 remains authority for shipping eligibility, zones, delivery methods, and checkout-address validation.

## Schema state

Accepted migration:

`apps/accounts/migrations/0002_address_alter_user_email_and_more.py`

It is a Django 5.2.17-generated migration and passes permanent migration-drift plus empty-PostgreSQL migration gates.

Do not manually replace it with a hand-authored migration unless a future phase has a documented schema reason and passes a new migration gate.

## CI state

Implementation END_SHA `2bd278034af122bb3c3a485160792fd5f0f1d434` passed:

- frozen dependencies
- Action pin verification
- secret sanity
- Ruff format/lint
- mypy
- Django checks
- migration drift
- migrate from zero on PostgreSQL 16.15
- all 24 tests
- OpenAPI validation
- production deployment policy
- bytecode compilation

The one-shot write-enabled migration workflow has been removed. Permanent CI is read-only for repository contents.

## Main-history note

B01 started from `4b118845cdbdf8159c5ef5e97252a7a9719588f6`.

Backend `main` later received two accidental documentation create/delete commits. At `efeb819cd998b4630859de2335f02aa5a0e8fb74`, comparison against the B01 start baseline contains **zero file changes**. Keep those neutral commits; do not force-push, rebase, or rewrite shared history merely to erase them.

## Deferred capabilities — do not misreport as B01

- password-reset delivery
- email verification delivery
- OTP / SMS authentication
- social login
- MFA
- staff/role/permission business policy
- account audit trail
- address deliverability / shipping zones
- catalog identity
- pricing/inventory/cart/order/payment authority

## B02 consumption rule

B02 may reference authenticated users where required for future ownership/audit hooks, but must not redefine identity or session policy.

Catalog entities must become backend production authority while frontend preview fixtures remain non-authoritative.

Pricing and inventory are not B02 authority; they remain B03.

Search ranking/full search authority remains B08.

## Closure sequence

1. Run Backend Quality Gate on this exact closure-documentation head.
2. Require SUCCESS before PR merge.
3. Create/update B01 PR with START_SHA, implementation END_SHA, closure SHA and CI evidence.
4. Confirm mergeability and zero unresolved review blockers.
5. Merge with the exact expected PR head SHA.
6. Require Backend Quality Gate SUCCESS on the resulting `main` merge SHA.
7. Close tracking issue #47 and update master issue #39.
8. Register B02 as NEXT.

## NEXT

`B02 — Catalog, Taxonomy, Variants & Media`
