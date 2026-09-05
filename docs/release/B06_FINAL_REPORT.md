# B06 — Orders & Order Lifecycle — Final Report

## Status

B06 application scope is **COMPLETED / MERGED / FROZEN / APPLICATION POST-MERGE GREEN**. This documentation-only registry transition records accepted evidence before B07 receives its exact START_SHA.

## Coordinates

- B06 START_SHA: `b44cb77cc3373c496c8e6d0ab251650ee6e48a95`
- implementation branch: `phase/visio-b06-orders-lifecycle`
- implementation END_SHA: `889e9b73f197a12fdbedb2ef650869024f53d806`
- closure/freeze head: `e910ac3ebae6231fdb6ae811f0ce5fbdf07e34ae`
- freeze ref: `freeze/visio-backend-b06-20260905`
- application PR: #12
- accepted application merge SHA: `89ec9234e56cf6908a10447b80f057e29730bfca`

## Delivered domain

B06 adds durable `Order` and `OrderLine` truth with immutable purchase snapshots, a separate public UUID identifier, user-scoped idempotent order creation, customer-scoped order APIs and an explicit forward-only lifecycle.

Order creation accepts only a B05 READY checkout identity plus an idempotency key. Before creation the server locks and revalidates the B05 checkout, current cart revision, checkout lines, authoritative prices, address/shipping/tax snapshots and active inventory reservations.

## Money and authority

- stored currency: IRR
- operational/display unit: تومان
- order totals are copied from the authoritative B05 checkout
- client-supplied status, total, currency or payment claims are not accepted as order truth
- DB constraints enforce nonnegative components and payable/line arithmetic

## Inventory handoff

Order creation preserves the active B03 reservation while status is `pending_payment`.

- verified-payment internal hook: consume reservation, then confirm order
- pending-payment customer cancellation: release reservation
- pending-payment expiry: release reservation
- no public payment-confirm endpoint exists

This leaves provider/payment truth exclusively for B07.

## Customer API

- `GET /api/v1/orders/`
- `POST /api/v1/orders/`
- `GET /api/v1/orders/{public_id}/`
- `POST /api/v1/orders/{public_id}/cancel/`

All endpoints use the accepted authenticated session boundary and enforce cross-user isolation.

## Lifecycle

Primary forward path:

`pending_payment -> confirmed -> processing -> shipped -> delivered`

Pre-payment terminal alternatives:

`pending_payment -> cancelled | expired`

Invalid backward/skipping transitions fail closed.

## Database and concurrency evidence

The PostgreSQL suite covers immutable snapshots, one-checkout-one-order, request idempotency, monetary constraints, stale checkout/price rejection, reservation release, single reservation consumption after verified payment, customer isolation, no public payment-confirm route, concurrent create serialization and confirmation-vs-cancellation race handling.

## Gate evidence

- implementation Gate #203 / run `33919923311` on `889e9b73f197a12fdbedb2ef650869024f53d806` — PASS
- closure Gate #206 / run `33920106400` on `e910ac3ebae6231fdb6ae811f0ce5fbdf07e34ae` — PASS
- PR exact-head Gate #207 / run `33974601876` on `e910ac3ebae6231fdb6ae811f0ce5fbdf07e34ae` — PASS
- unresolved PR review threads — 0
- PR #12 merged using expected head SHA
- accepted application merge: `89ec9234e56cf6908a10447b80f057e29730bfca`
- application post-merge Gate #208 / run `33974673956` — PASS
- migration drift — 0 / PASS
- migrate from empty PostgreSQL 16.15 — PASS
- full PostgreSQL test suite — **77/77 PASS**
- Ruff / strict mypy / Django checks / OpenAPI / deployment checks / action-pin and secret sanity / Python compilation — PASS

## Migration provenance

`apps/orders/migrations/0001_initial.py` was produced by Django 5.2.17 using `manage.py makemigrations orders`. Only mechanical formatting/import ordering was applied after generation; migration operations were not weakened or rewritten.

## B07 transition

B07 owns durable payment attempt/provider/reconciliation truth and may call `confirm_order_after_verified_payment()` only after authoritative provider verification succeeds. Redirect/callback parameters alone are not payment proof.

The exact B07 START_SHA is **not** the B06 application merge above. It becomes the resulting backend `main` SHA after this B06 registry documentation PR is reviewed, exact-head green, merged with expected SHA, and its post-merge Backend Quality Gate passes. That SHA must then be registered in the master/frontend trackers before B07 implementation begins.
