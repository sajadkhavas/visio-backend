# VISIO B04 — Cart & Wishlist Persistence

## Current Phase

B04 has started from the frozen B03 backend baseline.

## Baseline

- Previous accepted backend merge: `f28da671850879db3d1e1f74263aeb80cac54bdc`
- Branch: `phase/visio-b04-cart-wishlist-persistence`

## Completed before implementation

- B00 Backend Foundation: completed
- B01 Auth/User foundation: completed
- B02 Catalog: completed
- B03 Pricing & Inventory Integrity: completed

## B04 Scope

B04 is divided into:

### B04-A — Cart Domain Foundation

- Cart domain
- CartItem domain
- PostgreSQL constraints
- Django migrations
- Cart service layer
- Database integrity tests

### B04-B — Cart API

- API contracts
- Validation
- Ownership isolation

### B04-C — Wishlist

- WishlistItem
- Duplicate prevention
- API integration

### B04-D — Acceptance

- Ruff
- mypy strict
- Django checks
- migration drift
- PostgreSQL tests
- PR review
- Merge verification

## Current State

B04-A is active.

Repository architecture was reviewed before implementation:

- Existing apps: accounts, catalog, commerce, system
- Cart will integrate with ProductVariant from catalog.
- Cart does not reserve inventory; reservation remains part of checkout/order flow.

## Rules

- No direct main changes.
- No manual migration bypass.
- Django generated migrations only.
- Completion requires CI, merge and post-merge verification.
