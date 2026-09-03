# VISIO — B00 Backend Foundation Handoff

Date: 2026-09-03

## Resume point

Do not rebuild the B00 foundation. Continue from the accepted B00 branch/merge evidence and move to B01 only after the B00 closure gate is fully satisfied.

Backend repository:

`sajadkhavas/visio-backend`

B00 START_SHA:

`dbe0cba9c970bbd378f8f7af2d3beeb604db5e02`

Implementation END_SHA:

`2a10a2894e0d823822d2a1290933dfea44dbcaf9`

Working branch:

`phase/visio-b00-python-backend-foundation`

## What exists

- reproducibly locked Python/Django/DRF/PostgreSQL foundation;
- split local/test/production settings;
- first custom User migration;
- PostgreSQL-backed CI and migrate-from-zero;
- `/api/v1/`, `/health/`, `/ready/`, `/api/v1/schema/`;
- RFC 9457-style API errors;
- Ruff, mypy, pytest and Django system/deployment gates;
- immutable action pins and secret sanity;
- architecture and Python learning documentation.

## What does not exist yet

B00 deliberately does not define final customer authentication, phone/email/OTP policy, account/address API, catalog, variants, prices, stock, cart, wishlist, checkout, delivery, orders, payment, editorial/search authority or notification providers.

B01 owns identity/auth/account/address behavior and must start from this foundation rather than changing `AUTH_USER_MODEL` after the accepted first migration.

## HSTS deferral

`security.W005` and `security.W021` are explicitly deferred to R00/S00 because `includeSubDomains` and browser preload require a proven production DNS/TLS topology. All other deployment errors/warnings are blocking.

## Repository setting still required

The canonical repository is intended to be private. If GitHub still reports `sajadkhavas/visio-backend` as public, change repository visibility to Private before B00 is closed. No secret should be added before or after that change; secrets remain environment/server-managed.

## B01 entry rule

B01 may start only after:

- exact final B00 PR head quality gate PASS;
- zero blocking review threads;
- backend repository verified private;
- B00 PR merged;
- post-merge main quality gate PASS;
- B00 closure registered in VISIO master issue #39 and B00 issue #44.
