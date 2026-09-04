# B06 — Orders & Order Lifecycle — Final Report

## Coordinates

- B06 START_SHA: `b44cb77cc3373c496c8e6d0ab251650ee6e48a95`
- implementation branch: `phase/visio-b06-orders-lifecycle`
- implementation END_SHA: `889e9b73f197a12fdbedb2ef650869024f53d806`
- implementation Gate: Backend Quality Gate #203 / run `33919923311` — PASS

## Delivered domain

B06 adds durable `Order` and `OrderLine` truth with immutable purchase snapshots, a separate public UUID identifier, user-scoped idempotent order creation, customer-scoped order APIs and an explicit forward-only lifecycle.

Order creation accepts only a B05 READY checkout identity plus an idempotency key. Before creation the server locks and revalidates the B05 checkout, current cart revision, checkout lines, authoritative prices, address/shipping/tax snapshots and active inventory reservations.

## Money and authority

- stored currency: IRR
- operational/display unit: تومان
- order totals are copied from the authoritative B05 checkout
- client-supplied status, total, currency or payment claims are ignored/not accepted as order truth
- DB constraints enforce nonnegative components and payable/line arithmetic

## Inventory handoff

Order creation preserves the active B03 reservation while status is `pending_payment`.

- verified payment internal hook: consume reservation, then confirm order
- pending-payment customer cancellation: release reservation
- pending-payment expiry: release reservation
- no public payment-confirm endpoint exists

This leaves payment provider truth exclusively for B07.

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

The PostgreSQL suite covers:

- immutable product/variant/options/address/money snapshots;
- one checkout -> one order;
- request idempotency;
- DB monetary and line-total constraints;
- stale checkout/price rejection;
- reservation release on cancellation;
- reservation consume exactly once after verified payment;
- customer ownership/isolation;
- no public payment-confirm route;
- concurrent create for one checkout -> exactly one order;
- confirmation vs cancellation race -> one valid serialized outcome.

## Gate evidence

Backend Quality Gate #203 / `33919923311` on exact implementation head `889e9b73f197a12fdbedb2ef650869024f53d806`:

- frozen dependency install — PASS
- action pin verification — PASS
- secret sanity — PASS
- Ruff format — PASS
- Ruff lint — PASS
- strict mypy — PASS
- Django checks — PASS
- migration drift — 0 / PASS
- migrate from empty PostgreSQL 16.15 — PASS
- full PostgreSQL test suite — **77/77 PASS**
- OpenAPI generation/validation — PASS
- production deployment checks — PASS
- Python compilation — PASS

## Migration provenance

`apps/orders/migrations/0001_initial.py` was produced by Django 5.2.17 using `manage.py makemigrations orders`. Only mechanical Ruff formatting/import ordering was applied after generation; migration operations were not weakened or rewritten.

## B07 handoff

B07 must create durable payment attempt/provider/reconciliation truth. It may call `confirm_order_after_verified_payment()` only after authoritative provider verification succeeds. Redirect/callback parameters alone are not payment proof.

B06 is not considered closed until closure exact-head CI, freeze, PR exact-head CI, zero unresolved review threads, expected-SHA merge and post-merge main verification all pass.
