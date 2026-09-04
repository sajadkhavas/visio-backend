# VISIO B06 — Orders & Order Lifecycle — Handoff

## Resume truth

B06 implementation is complete and implementation-head CI is green. Closure/PR/merge evidence must still be completed before B06 is marked Done.

### Exact coordinates

- previous accepted backend main / B06 START_SHA: `b44cb77cc3373c496c8e6d0ab251650ee6e48a95`
- branch: `phase/visio-b06-orders-lifecycle`
- implementation END_SHA: `889e9b73f197a12fdbedb2ef650869024f53d806`
- implementation Gate #203 / run `33919923311`: PASS
- PostgreSQL suite: 77/77 PASS

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

## Closure steps still required at this handoff commit

1. exact closure-head Backend Quality Gate PASS;
2. create `freeze/visio-backend-b06-20260905` from the exact closure SHA;
3. backend PR to `main`;
4. PR-triggered exact-head Gate PASS;
5. unresolved blocking review threads = 0;
6. merge using expected head SHA;
7. post-merge `main` Gate PASS;
8. synchronize backend/frontend registries;
9. close tracker #54 and register exact B07 START_SHA in #55.

Do not start B07 from a pre-merge B06 SHA.
