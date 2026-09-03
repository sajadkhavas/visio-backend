# VISIO B01 — Identity / Authentication / Account / Address Handoff

Date: 2026-09-03

## Status

`B01_IMPLEMENTATION_COMPLETED / MERGED / POST_MERGE_GREEN`

The B01 application implementation is accepted. This evidence-only branch records the exact merge and post-merge gate. After this documentation is merged, the live phase/master trackers advance to B02.

## Immutable phase coordinates

- Backend repository: `sajadkhavas/visio-backend`
- Implementation branch: `phase/visio-b01-identity-auth-account-address`
- START_SHA: `4b118845cdbdf8159c5ef5e97252a7a9719588f6`
- Implementation END_SHA: `2bd278034af122bb3c3a485160792fd5f0f1d434`
- Closure/freeze SHA / PR #4 head: `a7119da44b55632185f1795119f4c7cd5237c58e`
- Freeze ref: `freeze/visio-backend-b01-20260903`
- Implementation PR: `#4 — B01: identity, authentication, account and address domain`
- Implementation merge SHA / accepted B01 application baseline: `af1cc61767f9f9c64d7b331630007fc414d90b1e`
- PostgreSQL test result: `24 passed`
- Final report: `docs/release/B01_FINAL_REPORT.md`
- Architecture decisions: `docs/architecture/B01_IDENTITY_AUTH_ACCOUNT_ADDRESS_DECISIONS.md`
- Implementation notes: `docs/architecture/B01_IMPLEMENTATION_NOTES.md`
- Python learning notes: `docs/learning/B01_AUTH_ACCOUNT_NOTES.md`

## Exact CI evidence

- Backend Quality Gate #53 / run `33773094652` on implementation END_SHA — PASS
- Backend Quality Gate #55 / run `33773366654` on closure/freeze SHA — PASS
- PR-triggered Backend Quality Gate #56 / run `33773545476` on exact PR #4 head — PASS
- unresolved review threads on PR #4 — 0
- PR #4 merged with expected head SHA — PASS
- post-merge Backend Quality Gate #57 / run `33773689986` on `af1cc61767f9f9c64d7b331630007fc414d90b1e` — PASS

The permanent gate verifies frozen dependencies, Action pins, secret sanity, Ruff, strict mypy, Django checks, migration drift, migrate-from-zero on PostgreSQL 16.15, all tests, OpenAPI, production deployment policy, and Python bytecode compilation.

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

It is Django 5.2.17-generated, has no rejected `AlterModelOptions` drift, and passes permanent migration-drift plus empty-PostgreSQL migration gates.

Do not manually replace it with a hand-authored migration unless a future phase has a documented schema reason and passes a new migration gate.

## Main-history note

B01 started from `4b118845cdbdf8159c5ef5e97252a7a9719588f6`.

Backend `main` later received two accidental documentation create/delete commits. At pre-B01 main `efeb819cd998b4630859de2335f02aa5a0e8fb74`, comparison against the B01 start baseline contained **zero file changes**. The shared history was preserved; no force-push/rebase/history rewrite was used merely to erase neutral commits.

## Deferred capabilities — do not misreport as B01

- password-reset delivery
- email verification delivery
- OTP / SMS authentication
- social login
- MFA
- staff/role/permission business policy
- account audit trail
- address deliverability / shipping zones
- catalog authority
- pricing/inventory/cart/order/payment authority

## B02 consumption rule

B02 may reference authenticated users where required for future ownership/audit hooks, but must not redefine identity or session policy.

Catalog entities must become backend production authority while frontend preview fixtures remain non-authoritative.

Pricing and inventory are not B02 authority; they remain B03.

Full search/ranking authority remains B08.

## Resume instruction

Do not redo B00 or B01.

Start B02 from the final backend `main` after this evidence-only documentation merge. Re-check current official Django/DRF/PostgreSQL guidance before B02 implementation and register a new B02 START_SHA.

## NEXT

`B02 — Catalog, Taxonomy, Variants & Media`
