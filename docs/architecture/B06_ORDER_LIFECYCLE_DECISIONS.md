# VISIO B06 — Order & Lifecycle Decisions

Date: 2026-09-04

## Coordinates

- exact START_SHA: `b44cb77cc3373c496c8e6d0ab251650ee6e48a95`
- branch: `phase/visio-b06-orders-lifecycle`
- tracker: frontend/master Issue #54

## Official references re-checked

- Django 5.2 database transactions: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- Django 5.2 model constraints: https://docs.djangoproject.com/en/5.2/ref/models/constraints/
- PostgreSQL 16 explicit/row locking: https://www.postgresql.org/docs/16/explicit-locking.html

Django `transaction.atomic()` remains the unit for all-or-nothing order/reservation transitions. PostgreSQL row locks protect checkout/order/reservation rows against concurrent writers until transaction end. Expressible invariants remain database constraints rather than serializer-only assumptions.

## Authority boundary

B06 owns durable order truth. B05 owns the short-lived READY checkout and authoritative pre-order validation. B07 will own payment-provider truth.

B06 must never mark an order paid because a browser says so and exposes no public endpoint that can assert payment success.

## Public identity

`Order.id` is the internal UUID primary key. `Order.public_id` is a separate opaque UUID4, unique and immutable, used by customer-facing API routes. Sequential database identifiers and customer/order volume are not exposed.

## Creation boundary

An order can only be created from an authenticated user's B05 checkout in `READY` state before its reservation expiry. The checkout is locked and one-to-one with the resulting order, so one checkout cannot create two orders.

Creation also accepts a UUID idempotency key scoped to the user. Repeating the same checkout returns the existing order. Reusing the same key for another checkout conflicts.

When order creation succeeds:

1. current READY checkout and lines are locked/revalidated;
2. every reservation must still be active, unexpired, quantity-matching and variant-matching;
3. customer/address/shipping/tax/money/catalog identity is copied into immutable snapshots;
4. the active cart is marked `converted`;
5. the checkout is marked `completed`;
6. the order starts in `pending_payment`.

Reservations are **not consumed at order creation**. They remain active while the order awaits B07 payment confirmation.

## Inventory handoff

B06 owns deterministic consume/release transitions around the order lifecycle:

- `pending_payment -> confirmed`: consume all active B03 reservations in deterministic variant order inside the same outer transaction;
- `pending_payment -> cancelled`: release active reservations;
- `pending_payment -> expired`: expire/release reservation state and close the order;
- later fulfillment states never silently mutate inventory again.

This avoids decrementing on-hand inventory before payment truth exists and prevents double consumption.

## Lifecycle

Accepted statuses:

- `pending_payment`
- `confirmed`
- `processing`
- `shipped`
- `delivered`
- `cancelled`
- `expired`

Allowed state transitions:

- `pending_payment -> confirmed` (internal B07 integration only)
- `pending_payment -> cancelled` (customer cancellation before payment)
- `pending_payment -> expired` (reservation/checkout expiry)
- `confirmed -> processing`
- `processing -> shipped`
- `shipped -> delivered`

No backward or arbitrary transition is accepted. B09 staff tooling must call the same domain transition service rather than bypassing it.

## Immutable snapshots

`Order` snapshots:

- address JSON copied from B05;
- shipping JSON copied from B05;
- subtotal, discount, shipping, tax, payable and tax-rate values;
- canonical money metadata (`IRR`, `تومان`).

`OrderLine` snapshots:

- source product UUID, slug and name;
- source variant UUID and SKU;
- deterministic option-selection JSON;
- quantity;
- unit price and line total.

Order APIs provide no mutation surface for snapshot fields. Lifecycle services only modify status/timestamps. Snapshot tests must prove later catalog/address/price changes do not change historical order output.

## Monetary invariants

All amounts stay integer Toman in `DecimalField(..., decimal_places=0)`, never float. Database checks enforce non-negative components, discount <= subtotal, payable component equality and line-total equality.

## Customer API

B06 exposes authenticated customer endpoints:

- `POST /api/v1/orders/` — create/idempotently retrieve from a READY checkout;
- `GET /api/v1/orders/` — current user's order history;
- `GET /api/v1/orders/<public_id>/` — current user's order detail;
- `POST /api/v1/orders/<public_id>/cancel/` — cancellation only while `pending_payment`.

There is intentionally no customer or staff HTTP endpoint in B06 to claim payment confirmation. B07 will integrate with the internal confirmed-payment transition after verified provider truth exists.

## Concurrency requirements

PostgreSQL tests must prove:

- two concurrent create attempts for one checkout result in exactly one durable Order;
- repeated idempotent create does not duplicate lines or consume reservations;
- concurrent payment-confirm transitions cannot double-consume inventory;
- cancellation/confirmation races serialize under row locks and produce one valid terminal outcome;
- cross-user read/cancel/create access fails closed.

## Non-goals

- provider/payment attempts/callback/reconciliation/refund — B07;
- admin operations — B09;
- external event bus/queue/microservice infrastructure.
