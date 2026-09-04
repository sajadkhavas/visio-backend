# VISIO B05 — Checkout, Address Validation, Shipping & Delivery Decisions

Status: FROZEN FOR IMPLEMENTATION  
Date: 2026-09-04  
START_SHA: `edce938b6640d6dffc9730024a00dfc7a96323f5`  
Branch: `phase/visio-b05-checkout-shipping-delivery`

## 1. Authority boundary

B05 is the final pre-order authority. It never trusts browser totals, browser price snapshots, browser availability, browser shipping rates or browser tax amounts.

Accepted inputs are identifiers and idempotency keys only. Every price, stock, address-eligibility, shipping and tax decision is resolved from backend state.

B06 remains the owner of durable Order/OrderLine truth. B07 remains the owner of payment-provider truth.

## 2. Frontend contract audit

The frozen frontend `CheckoutDraft` contains cart lines and explicitly sets `requiresServerValidation: true`. It is therefore a request/UX snapshot, not order truth.

B05 operates on the authenticated B04 cart already persisted by the server. Client-provided checkout lines/totals are not accepted as an authoritative checkout payload.

## 3. Checkout session

`CheckoutSession` is user-owned and tied to the user's active B04 cart and a user-owned B01 address.

At most one non-terminal checkout (`active` or `ready`) may exist per user. Starting a new checkout with a new idempotency key cancels the previous non-terminal checkout and releases its active reservations.

Creation is idempotent by `(user, idempotency_key)`. Reusing the same key with different address/shipping inputs is a conflict and never silently changes the original request.

Checkout sessions are bounded by the B03 reservation TTL. They do not extend reservations on read.

## 4. Cart and price validation

Checkout creation locks the B04 cart before reading final lines. Each line must resolve to an active variant of a published product and an active B03 price record.

The server stores a server-generated checkout price snapshot (`unit_price_toman`, `line_total_toman`) solely as the validated pre-order handoff state. Browser price snapshots are ignored.

Finalization rechecks cart revision, line identities/quantities and current B03 price records. Any change fails closed and requires a new checkout session.

Canonical money remains integer Toman operationally with currency identity `IRR` and display unit `تومان`.

## 5. Inventory reservation

Ordinary B04 cart mutation still creates no reservation.

B05 creates B03 `InventoryReservation` records only while creating an authenticated checkout session. Variants are processed in deterministic UUID order so concurrent multi-line checkout attempts acquire inventory locks consistently.

All line reservations are created under the outer B05 atomic transaction. A failure on any line rolls back the whole checkout and all newly created reservations.

Reservations are not consumed in B05. B06 owns the consume/release handoff when durable order truth is introduced.

## 6. Address eligibility

The address must be a B01 `Address` owned by the authenticated user.

Eligibility is determined by configured `ShippingZone` rows. A zone can be country-, province-, or city-specific. The most specific matching active zone wins. Ambiguous equal-specificity matches fail closed.

A server-generated address snapshot is stored on the checkout session so later address-book edits cannot silently change an already validated handoff. Finalization compares the current owned address to the stored snapshot and fails if it changed.

## 7. Shipping authority

B05 introduces backend `ShippingZone` and `ShippingMethod` configuration.

A method belongs to one zone and owns its flat rate, optional free-shipping threshold and optional delivery-day estimate. The selected method must be active and belong to the currently resolved address zone.

No carrier/provider API is claimed in B05. No external shipping provider has been selected or proven by current official provider documentation. The B05 contract is intentionally provider-neutral; later provider wiring must be justified by actual official capability.

No scheduled delivery-window calendar is invented. Optional min/max delivery days are informational backend configuration only.

If no eligible zone or active method exists, checkout fails closed.

## 8. Tax and discount policy

Tax is never hard-coded from a legal assumption. `CheckoutTaxPolicy` is explicit backend configuration keyed by country and stores basis points plus whether shipping is taxable.

If no active tax policy exists for the destination country, checkout fails closed. A zero tax rate is valid only when an explicit active policy row says zero.

B05 has no accepted promotion/coupon domain. Discount therefore remains an explicit server-authoritative zero in B05; a later discount feature must introduce its own authority and tests rather than trusting a browser discount.

Tax is rounded to the nearest integer Toman using decimal `ROUND_HALF_UP`.

## 9. Final totals

B05 computes:

`subtotal = sum(server unit price × quantity)`  
`discount = 0`  
`shipping = selected backend shipping rule`  
`tax = configured tax policy over its configured taxable base`  
`payable = subtotal - discount + shipping + tax`

All persisted monetary fields are non-negative and the session payable amount is constrained to equal the component formula.

## 10. Finalize / B06 handoff

`POST finalize` is idempotent. A client supplies a UUID idempotency key; the first successful finalization stores that key and moves the checkout to `ready`. Repeating with the same key returns the same ready handoff. Repeating with a different key conflicts.

Finalization does not create an Order and does not consume stock. It revalidates cart revision, address snapshot, shipping configuration, tax configuration, current prices and every active reservation.

The B06 handoff consists of the checkout ID, cart revision, authoritative server snapshots/totals and reservation-backed expiry boundary. B06 must still own order-creation idempotency and immutable order snapshots.

## 11. Locking order

Within a checkout mutation, locks are acquired in a deterministic order:

1. authenticated User row;
2. previous non-terminal checkout/reservations when replacing one;
3. active Cart row and CartLine rows;
4. variant/price truth in deterministic variant order;
5. B03 inventory rows through `reserve_variant()` in deterministic variant order;
6. CheckoutSession final state.

Transactions remain short and contain no network calls.

## 12. API surface

Versioned authenticated endpoints:

- `GET /api/v1/checkout/shipping-options/?addressId=<uuid>`
- `GET /api/v1/checkout/current/`
- `POST /api/v1/checkout/sessions/`
- `POST /api/v1/checkout/sessions/<checkout_id>/finalize/`
- `POST /api/v1/checkout/sessions/<checkout_id>/cancel/`

All mutation endpoints retain B01 session authentication + CSRF behavior.

## 13. Required tests

- address ownership and serviceability isolation;
- deterministic zone specificity and ambiguous-config fail-closed behavior;
- explicit tax-policy requirement;
- server-only repricing and totals;
- no trust in browser totals/price snapshots;
- all-or-nothing multi-line reservation creation;
- concurrent stock contention without oversell;
- one non-terminal checkout per user;
- create-idempotency and conflict behavior;
- cart/address/price/shipping/tax staleness at finalize;
- finalize idempotency;
- cancellation releases reservations;
- reservation expiry blocks finalize;
- cross-user checkout isolation;
- Django-generated migrations, drift=0, migrate-from-empty PostgreSQL 16.15;
- full suite, OpenAPI, Ruff, strict mypy, Django deployment and secret gates.

## 14. Official references re-checked

- Django 5.2 transactions: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- Django 5.2 `select_for_update()`: https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update
- Django 5.2 constraints: https://docs.djangoproject.com/en/5.2/ref/models/constraints/
- DRF authentication: https://www.django-rest-framework.org/api-guide/authentication/
- DRF permissions: https://www.django-rest-framework.org/api-guide/permissions/
- DRF serializers/validation: https://www.django-rest-framework.org/api-guide/serializers/
- PostgreSQL 16 concurrency control: https://www.postgresql.org/docs/16/mvcc.html
- PostgreSQL 16 transaction isolation: https://www.postgresql.org/docs/16/transaction-iso.html

## 15. Explicit non-goals

- carrier/provider API integration without selected/proven provider capability;
- scheduled delivery-slot orchestration without operational source of truth;
- promotions/coupons without a separate authority model;
- Order/OrderLine creation — B06;
- payment — B07;
- frontend production integration — I00;
- Redis/Celery/queues/microservices for checkout.
