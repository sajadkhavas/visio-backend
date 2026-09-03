# B04 — Cart & Wishlist Persistence Decisions

Date: 2026-09-04
Status: Accepted for implementation; final acceptance still requires exact-head CI, PR merge and post-merge verification.

## Entry

B04 START_SHA is the accepted B03 backend main:

`f28da671850879db3d1e1f74263aeb80cac54bdc`

Implementation branch:

`phase/visio-b04-cart-wishlist-persistence`

## Official guidance re-checked

Before implementation the phase re-checked current Django 5.2 constraint and transaction guidance plus current Django REST Framework serializer, authentication and permission guidance.

Accepted consequences:

- database uniqueness is the final integrity layer for one active cart and one variant per cart;
- short `transaction.atomic()` blocks plus `select_for_update()` serialize competing mutations against the same cart row;
- DRF validation protects the API boundary but does not replace database constraints;
- all cart/wishlist endpoints require authenticated session identity; unsafe SessionAuthentication requests remain CSRF protected.

## Authority boundaries

### Cart

`Cart` is owned by exactly one authenticated user. A conditional database `UniqueConstraint` permits at most one `active` cart per user.

`Cart.revision` is server synchronization metadata. It is intentionally separate from the frontend `Cart.version`, because the frozen frontend contract defines `version = 2` as the browser persistence schema version, not a mutable server revision.

### CartLine

A line stores only authoritative server identity and quantity:

- `ProductVariant` FK;
- quantity;
- timestamps.

Product ID, selected options and deterministic cart key are derived from catalog truth. Client-supplied product/options/key are not stored as authority.

A database unique constraint enforces one line per `(cart, variant)`. Quantity is database-bounded to `1..99`.

### Price

No authoritative price is persisted on CartLine. Every cart read/validation projects current price from B03 `VariantPrice` via the accepted B03 projection layer.

Client price snapshots may be sent only for mismatch UX. They are compared with current B03 price and can produce `price-changed`; they never replace server price.

### Inventory

Ordinary cart mutations do not create `InventoryReservation` records and never guarantee stock.

Cart reads project B03 available-to-promise. Validation may reduce a persisted quantity to a positive current authoritative maximum, but sold-out lines remain persisted at minimum quantity 1 and are reported as `sold-out`. B05 owns final checkout repricing, stock validation and reservation.

### Browser guest import

Anonymous browser cart remains client-local.

After authentication, B04 accepts a bounded import payload of at most 100 lines. Duplicate guest variants are summed and capped at 99. Merge with existing server state uses `max(existing_quantity, imported_quantity)`, making repeated import of the same browser state idempotent at the resulting cart-state level.

Unavailable/inactive variants are skipped with explicit import issues rather than silently becoming server truth.

### Wishlist

Wishlist persistence is `user + Product` with a database unique constraint. Add and delete are idempotent. Only published products can be newly added.

## Frozen frontend identity compatibility

The server reproduces the frozen frontend deterministic key algorithm:

1. derive option selections from the authoritative variant;
2. sort by option key;
3. URI-component encode names and values;
4. join as `name=value&...`;
5. key = `productId::variantId::optionPart`, falling back to `default` when no options exist.

Frontend persistence `version=2` remains unchanged.

## API contract

All routes are under `/api/v1/`:

- `GET /cart/` — current cart;
- `DELETE /cart/` — clear current cart;
- `POST /cart/lines/` — add/increment variant;
- `PATCH /cart/lines/{variantId}/` — set quantity;
- `DELETE /cart/lines/{variantId}/` — remove line;
- `POST /cart/validate/` — current B03 validation and price mismatch projection;
- `POST /cart/import/` — authenticated browser-cart merge;
- `GET /wishlist/` — product IDs;
- `PUT /wishlist/{productId}/` — idempotent add;
- `DELETE /wishlist/{productId}/` — idempotent remove.

## Transaction/concurrency strategy

- Active-cart creation is protected by the conditional unique constraint and retry-after-integrity-conflict logic.
- Mutations lock the active `Cart` row with `select_for_update()` inside short atomic blocks.
- Duplicate concurrent adds serialize on the same cart and cannot create duplicate lines.
- Database constraints remain the final protection if application-level sequencing is bypassed.

## Explicit non-goals

- stock reservation on add-to-cart;
- anonymous server cart tokens;
- checkout/shipping/address eligibility;
- order creation;
- payment;
- Redis/Celery/queues/microservices.

Those remain later registered phases.
