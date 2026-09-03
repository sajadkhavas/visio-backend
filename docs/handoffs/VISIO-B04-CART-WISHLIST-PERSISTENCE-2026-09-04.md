# VISIO B04 Handoff — Cart & Wishlist Persistence

Date: 2026-09-04

## Resume coordinates

- backend repository: `sajadkhavas/visio-backend`
- B04 START_SHA: `f28da671850879db3d1e1f74263aeb80cac54bdc`
- implementation branch: `phase/visio-b04-cart-wishlist-persistence`
- implementation END_SHA: `b4205601ad04105a6da2f6080754a8f6eefa20ba`
- implementation Gate #143 / `33816115318`: PASS

Do not mark B04 complete from this handoff alone. Closure-head Gate, freeze, PR, expected-SHA merge and post-merge main verification remain mandatory until registered as completed.

## Accepted implementation truth

B04 now owns authenticated cart and wishlist persistence.

### Cart

- one active Cart per user is database-enforced;
- CartLine identity is authoritative ProductVariant + quantity;
- one variant per cart is database-enforced;
- quantity is database/API bounded to 1..99;
- server `revision` is separate from frontend persistence `version=2`;
- add/set/remove/clear are transactionally serialized on the active cart;
- duplicate concurrent adds cannot leave duplicate rows;
- ordinary cart mutation does not reserve inventory.

### B03 projection

Cart reads/validation derive price and available-to-promise from B03. CartLine stores no authoritative money. Client price snapshots can only produce mismatch UX and never become server price truth.

### Browser import

Guest state remains browser-local until authentication. Authenticated import is bounded to 100 raw lines, deduplicates variants deterministically, skips unavailable variants explicitly and uses result-state-idempotent merge semantics.

### Wishlist

Wishlist is user + Product persistence. Add/remove are idempotent and isolated by authenticated user identity.

## API routes

All under `/api/v1/`:

- `GET|DELETE cart/`
- `POST cart/lines/`
- `PATCH|DELETE cart/lines/{variantId}/`
- `POST cart/validate/`
- `POST cart/import/`
- `GET wishlist/`
- `PUT|DELETE wishlist/{productId}/`

## Database migration

`cart.0001_initial` was produced by Django 5.2.17. Temporary migration/format helper workflows were removed before implementation acceptance.

## Quality evidence

Exact implementation head Gate #143 / `33816115318` passed:

- frozen install;
- action-pin and secret checks;
- Ruff format/lint;
- strict mypy;
- Django system check;
- migration drift=0;
- migrate-from-empty PostgreSQL 16.15;
- 55/55 tests;
- OpenAPI validation;
- production deployment check;
- bytecode compilation.

## Known phase boundary

B04 does not own checkout addresses, shipping, delivery, final price/stock validation, inventory reservation, orders or payment.

After B04 post-merge closure, transition only to registered Issue #53 / B05 — Checkout, Address Validation, Shipping & Delivery.

## Next closure sequence

`final docs head → exact closure Gate → freeze/visio-backend-b04-20260904 → PR → PR exact-head Gate → zero blocking review threads → expected-head-SHA merge → post-merge main Gate → close #52 → B05 #53 NEXT → master/current-status sync`
