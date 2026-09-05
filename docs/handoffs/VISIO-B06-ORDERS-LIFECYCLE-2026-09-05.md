# VISIO B06 — Orders & Order Lifecycle — Handoff

## Resume truth

B06 application scope is complete, merged, frozen and post-merge green. This docs-only registry transition is the final step before B07 receives its exact START_SHA.

### Exact coordinates

- previous accepted backend main / B06 START_SHA: `b44cb77cc3373c496c8e6d0ab251650ee6e48a95`
- implementation branch: `phase/visio-b06-orders-lifecycle`
- implementation END_SHA: `889e9b73f197a12fdbedb2ef650869024f53d806`
- closure/freeze head: `e910ac3ebae6231fdb6ae811f0ce5fbdf07e34ae`
- freeze: `freeze/visio-backend-b06-20260905`
- application PR #12: MERGED
- accepted application merge: `89ec9234e56cf6908a10447b80f057e29730bfca`

### Accepted evidence

- implementation Gate #203 / run `33919923311`: PASS
- closure Gate #206 / run `33920106400`: PASS
- PR exact-head Gate #207 / run `33974601876`: PASS
- PR unresolved blocking review threads: 0
- application merge used expected head SHA `e910ac3ebae6231fdb6ae811f0ce5fbdf07e34ae`
- application post-merge Gate #208 / run `33974673956`: PASS
- PostgreSQL suite: 77/77 PASS
- migration drift: 0
- migrate-from-zero PostgreSQL 16.15: PASS

## Implemented files and boundaries

- `apps/orders/models.py` — durable Order/OrderLine snapshots + DB invariants
- `apps/orders/services.py` — idempotent creation, cancellation, expiry, payment-confirm handoff, fulfillment transitions
- `apps/orders/selectors.py` — customer-scoped reads
- `apps/orders/serializers.py` — immutable API projection
- `apps/orders/api_views.py` / `api_urls.py` — authenticated customer API only
- `apps/checkout/order_bridge.py` — B05 READY checkout locked revalidation bridge
- `apps/orders/migrations/0001_initial.py` — Django 5.2.17 generated
- `tests/test_b06_orders.py` — ownership/integrity/idempotency/race/lifecycle coverage

## Invariants future work must preserve

1. Order creation happens only from a revalidated B05 READY checkout.
2. Historical Order/OrderLine output is snapshot-based; later catalog/address/price edits do not rewrite history.
3. One CheckoutSession can produce at most one Order.
4. User + idempotency key is unique.
5. Order creation leaves reservation ACTIVE while payment is pending.
6. Only verified-payment internal handoff can consume reservation and confirm order.
7. Cancellation/expiry before payment releases reservation.
8. Customer cannot assert payment success or fulfillment state through public API.
9. Lifecycle is forward-only.
10. IRR/تومان and arithmetic DB constraints remain authoritative.

## B07 integration contract

B07 owns payment truth. After provider verification—not merely redirect/callback receipt—it may invoke:

`confirm_order_after_verified_payment(order_id)`

That transition locks the Order and consumes the B03 reservations exactly once before status becomes confirmed. B07 must keep provider attempt/idempotency/reconciliation records separate from the immutable B06 order snapshot.

## Final transition rule

Do not start B07 from the application merge SHA `89ec9234e56cf6908a10447b80f057e29730bfca`.

The exact B07 START_SHA is the backend `main` SHA produced after this docs-only registry PR:

1. passes exact-head Backend Quality Gate;
2. has zero unresolved blocking review threads;
3. merges using expected head SHA;
4. passes post-merge `main` Backend Quality Gate.

After that, close frontend/master tracker #54 and register that exact final `main` SHA plus the dedicated B07 branch in tracker #55.
