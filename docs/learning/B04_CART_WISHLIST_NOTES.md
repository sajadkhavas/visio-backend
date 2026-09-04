# B04 — Cart & Wishlist Learning Notes

Date: 2026-09-04

## Why the server cart stores a variant, not browser identity fields

The frozen frontend builds a cart identity from product ID, variant ID, normalized options and a deterministic key. On the backend, `ProductVariant` is already the authoritative selectable catalog identity. Therefore B04 stores the variant FK and quantity, then derives product/options/key for responses. This avoids allowing client-supplied product IDs, option maps or keys to become a second source of truth.

## Why `Cart.version` and server revision are separate

The frontend contract defines cart persistence `version = 2` as a schema/persistence version. Reusing that field as an optimistic-lock counter would silently change its meaning. B04 therefore keeps response `version=2` and uses `Cart.revision` / `serverRevision` as mutable synchronization metadata.

## Why add-to-cart does not reserve stock

Cart membership expresses intent, not a stock guarantee. B03 already owns inventory and reservation truth. Reserving during ordinary cart mutations would allow abandoned carts to consume sellable stock and would blur the B04/B05 authority boundary. B04 only projects current B03 availability; B05 will own final checkout validation and reservation.

## Concurrency pattern

Expressible invariants are enforced in PostgreSQL:

- one active Cart per user;
- one CartLine per `(cart, variant)`;
- line quantity between 1 and 99;
- one WishlistItem per `(user, product)`.

Mutation services use short `transaction.atomic()` blocks and lock the active Cart row with `select_for_update()`. This serializes competing mutations to the same cart while database constraints remain the final safety layer.

## Browser-cart merge semantics

Guest cart remains browser-local. Authenticated import is bounded to 100 raw lines. Duplicate imported variants are summed and capped at 99. When the same variant already exists server-side, the merged quantity is `max(existing, imported)`. Repeating the same import therefore does not keep incrementing quantity and is idempotent at resulting-state level.

## Price mismatch UX without price authority leakage

A client snapshot can be supplied for comparison. The server always obtains current price from the B03 projection. If the snapshot differs, B04 returns a `price-changed` issue and both previous/current snapshots for UX, but the client amount is never persisted or used as the current price.

## Defects caught during implementation

### 1. Nested enum scope in `Meta`

The first Django migration-generation run failed before generating a migration because `Cart.Meta` referenced `Status.ACTIVE` directly. Python class-body scoping did not resolve that nested enum inside `Meta`. The conditional uniqueness definition was corrected to `Q(status="active")`; the invariant was unchanged.

### 2. Strict typing caught variable shadowing

The first full type gate reached strict mypy and found that a local name used for `BrowserCartLine` was later reused for a Django `CartLine`. That made the inferred type incorrect and exposed unsafe mutation assumptions. Separate names (`raw_line`, `cart_line`) fixed the issue without weakening mypy.

### 3. Generated migration lint normalization

Django generated `cart.0001_initial` successfully. Ruff then requested import ordering normalization in that generated file. Only import order was changed; migration operations and schema semantics were not hand-authored or altered.

## Gate evidence

Implementation END:

`b4205601ad04105a6da2f6080754a8f6eefa20ba`

Backend Quality Gate #143 / run `33816115318`: PASS.

Evidence included:

- frozen dependency install;
- immutable action-pin check;
- secret sanity;
- Ruff format/lint;
- strict mypy: no issues in 58 source files;
- Django system checks;
- migration drift: no changes detected;
- migrate-from-zero on PostgreSQL 16.15;
- full test suite: 55 passed;
- OpenAPI validation;
- production deployment checks;
- bytecode compilation.
