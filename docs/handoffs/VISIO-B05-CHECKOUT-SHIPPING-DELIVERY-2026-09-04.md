# VISIO B05 — Checkout, Address Validation, Shipping & Delivery — Handoff

## Resume coordinates

- accepted B04 / B05 START_SHA: `edce938b6640d6dffc9730024a00dfc7a96323f5`
- implementation branch: `phase/visio-b05-checkout-shipping-delivery`
- implementation END_SHA: `85d76d5da90eae5e6f41e37383a0711a216f27da`
- implementation Gate #169 / run `33857601572`: PASS
- tracker: frontend/master Issue #53

## Accepted B05 contract at implementation gate

B05 converts an authenticated B04 cart into a short-lived server-validated checkout statement. It owns final pre-order repricing, address validation, shipping/tax policy resolution, inventory reservations, authoritative totals and an idempotent READY handoff to B06.

It does not create an order, interact with a payment provider or consume stock. B06 owns durable orders and the consume/release transition; B07 owns payment truth.

## API

- `GET /api/v1/checkout/shipping-options/?addressId=<id>`
- `GET /api/v1/checkout/current/`
- `POST /api/v1/checkout/sessions/`
- `POST /api/v1/checkout/sessions/<uuid>/finalize/`
- `POST /api/v1/checkout/sessions/<uuid>/cancel/`

All endpoints require the existing authenticated B01 session boundary. Mutation requests contain identifiers/idempotency keys only; browser money values are not authoritative inputs.

## Persistence

- `ShippingZone`
- `ShippingMethod`
- `CheckoutTaxPolicy`
- `CheckoutSession`
- `CheckoutLine`

The initial migration was generated with Django 5.2.17. PostgreSQL constraints protect one non-terminal checkout/user, per-user idempotency keys, money bounds/component equality, line identity/quantity and line-total equality.

## Concurrency

Checkout creation locks relevant user/cart/policy rows and delegates variant reservation to the B03 locking service. Reservation order is deterministic. The PostgreSQL race test with stock=1 and two users proves exactly one checkout obtains the reservation.

## Fail-closed conditions

Checkout refuses to proceed when any of these are missing/stale/ambiguous:

- authenticated user-owned address;
- active cart with lines;
- active published product/variant;
- active server price;
- authoritative inventory;
- unique matching shipping zone;
- active selected shipping method;
- active destination tax policy;
- active non-expired reservation;
- unchanged cart/address/price/shipping/tax/totals at finalize.

## NEXT after closure

Do not start B06 until B05 closure requirements all pass: closure exact-head Gate, freeze, PR exact-head Gate, zero unresolved review threads, expected-SHA merge, post-merge main Gate and registry sync. The final registry-synced backend main SHA becomes the exact B06 START_SHA.
