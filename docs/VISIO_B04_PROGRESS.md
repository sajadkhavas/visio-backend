# VISIO B04 — Cart & Wishlist Persistence

## Final State

B04 is **COMPLETED / MERGED / FROZEN / POST-MERGE GREEN**.

## Final coordinates

- START_SHA: `f28da671850879db3d1e1f74263aeb80cac54bdc`
- implementation branch: `phase/visio-b04-cart-wishlist-persistence`
- implementation END_SHA: `b4205601ad04105a6da2f6080754a8f6eefa20ba`
- closure/freeze head: `13328a764ec2e87651bc6e7ce413a999fb6afab7`
- freeze ref: `freeze/visio-backend-b04-20260904`
- PR #8: MERGED with expected head SHA
- accepted B04 application merge: `9a128c8f92f40f9d5b3bf3b3a493b9f59ce1c605`

## Gate evidence

- implementation Gate #143 / run `33816115318` — PASS
- closure Gate #146 / run `33816407274` — PASS
- PR exact-head Gate #147 / run `33840685756` — PASS
- post-merge main Gate #148 / run `33840758239` — PASS
- unresolved PR review threads: 0
- PostgreSQL full suite: 55/55 PASS
- migration drift: 0
- migrate-from-empty PostgreSQL 16.15: PASS
- Ruff / strict mypy / Django / OpenAPI / deployment / secret/action-pin gates: PASS

## Accepted domain behavior

- authenticated Cart / CartLine / Wishlist persistence
- one active cart per user DB invariant
- one variant per cart line DB invariant
- quantity constrained to 1..99
- add / set / remove / clear cart operations
- bounded deterministic browser-cart import/merge
- idempotent wishlist list/add/remove
- cross-user isolation
- B03 server-authoritative price/availability projection
- client price snapshots never become server authority
- ordinary cart mutation creates no InventoryReservation
- Django 5.2.17 generated migration
- PostgreSQL integrity/concurrency/ownership tests

## Documentation

- `docs/architecture/B04_CART_WISHLIST_DECISIONS.md`
- `docs/learning/B04_CART_WISHLIST_NOTES.md`
- `docs/release/B04_FINAL_REPORT.md`
- `docs/handoffs/VISIO-B04-CART-WISHLIST-PERSISTENCE-2026-09-04.md`

## NEXT

B05 — Checkout, Address Validation, Shipping & Delivery — frontend master Issue #53.

The accepted B04 application merge is `9a128c8f92f40f9d5b3bf3b3a493b9f59ce1c605`. Because this closure registry is being merged through a docs-only PR after application acceptance, the exact B05 START_SHA must be the resulting post-registry backend `main` SHA after its post-merge Gate passes.

Do not redo B04.