# B06 — Order Lifecycle Notes

## Purpose

B06 turns the fully validated B05 checkout boundary into durable order truth without allowing the browser or payment redirect to become commerce authority.

## Durable snapshot rule

Order and OrderLine copy the customer/address/shipping/money/product/variant/option values needed to understand the purchase later. Catalog, address-book and price rows can change after order creation without rewriting historical order meaning.

The stored money contract remains IRR with the operational/display unit تومان. Order totals are copied only from the locked and revalidated B05 checkout; client totals are never accepted.

## Reservation lifecycle

Creating an order from a READY checkout does not consume stock. The B03 reservation remains ACTIVE while the order is `pending_payment`.

Only the internal `confirm_order_after_verified_payment()` boundary may move `pending_payment -> confirmed`, and it consumes every reservation exactly once. B07 must call this only after provider payment truth has been verified.

Customer cancellation or order expiry is allowed only from `pending_payment` and releases the reservations. Confirm-vs-cancel races serialize through PostgreSQL row locks, so one valid terminal result wins.

## State machine

Accepted forward lifecycle:

`pending_payment -> confirmed -> processing -> shipped -> delivered`

Alternative pre-payment endings:

`pending_payment -> cancelled`

`pending_payment -> expired`

Backward fulfillment transitions are rejected. Replaying an already-completed exact transition is harmless where explicitly implemented.

## Idempotency

Order creation is protected at two levels:

- one Order per CheckoutSession through a one-to-one DB relation;
- unique `(user, idempotency_key)` for request replay protection.

The user row and relevant checkout/order rows are locked so concurrent create attempts for the same checkout serialize to one durable order.

## Public API boundary

Authenticated customers can:

- create an order from their own READY checkout;
- list their own orders;
- retrieve one of their own orders by `public_id`;
- cancel their own pending-payment order.

There is intentionally no public endpoint that lets a customer assert payment success or force a fulfillment state.

## Verification lessons

The B06 implementation exposed two useful gate defects before acceptance:

1. Django-generated migration formatting/import order required the same mechanical Ruff normalization used in earlier phases. Migration operations were not altered.
2. drf-spectacular initially generated a duplicate `operationId` for list and detail GET endpoints. Explicit unique operation IDs removed the schema warning; the deployment gate correctly treated new OpenAPI warnings as release blockers.

Final implementation evidence on `889e9b73f197a12fdbedb2ef650869024f53d806`:

- Backend Quality Gate #203 / run `33919923311` — PASS
- PostgreSQL 16.15 full suite — 77/77 PASS
- migration drift — 0
- migrate-from-empty — PASS
- Ruff format/lint — PASS
- strict mypy — PASS
- Django checks — PASS
- OpenAPI validation — PASS without operationId collision
- production deployment checks — PASS
- secret/action-pin checks — PASS
