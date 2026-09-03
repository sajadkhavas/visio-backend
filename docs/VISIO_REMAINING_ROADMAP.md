# VISIO Remaining Delivery Roadmap

## Current Accepted Baseline

Current backend main baseline after completed phases:

- B00 Backend Foundation: COMPLETED
- B01 Identity/Auth/Account/Address: COMPLETED
- B02 Catalog/Taxonomy/Variants/Media: COMPLETED
- B03 Pricing/Inventory Integrity: COMPLETED

Current baseline:

`f28da671850879db3d1e1f74263aeb80cac54bdc`

---

## Execution Rules

All future phases must follow:

- Never change main directly.
- Create phase branch from accepted SHA.
- Use official Django/DRF/PostgreSQL documentation as source of decisions.
- Do not write migrations manually unless there is a documented exception.
- Generate migrations with Django.
- Run full quality gates before completion.
- Completion requires:
  - tests green
  - CI green
  - PR review complete
  - merge
  - post-merge verification
  - registry update

---

# Remaining Phases

## B04 — Cart & Wishlist Persistence

Status: IN PROGRESS

Baseline:
`f28da671850879db3d1e1f74263aeb80cac54bdc`

Sub phases:

### B04-A Cart Domain Foundation

- Create cart application
- Cart model
- CartItem model
- Active cart lifecycle
- Variant based cart ownership
- Quantity rules
- PostgreSQL constraints
- Service layer
- Migration
- Database tests

### B04-B Cart API

- Cart serializers
- Cart endpoints
- Ownership isolation
- Quantity validation
- Catalog/pricing validation
- OpenAPI update

### B04-C Wishlist

- WishlistItem model
- Duplicate prevention
- User isolation
- API endpoints
- Tests

### B04-D Acceptance

- Ruff
- mypy strict
- Django checks
- migration drift
- migrate from zero
- PostgreSQL tests
- OpenAPI
- PR
- Merge
- Post merge verification

---

## B05 — Checkout Foundation

Planned:

- Checkout lifecycle
- Address selection
- Cart validation
- Price revalidation
- Inventory reservation integration

---

## B06 — Order Domain

Planned:

- Order model
- Order items
- Order state machine
- Immutable order snapshots
- Customer order history

---

## B07 — Payment

Planned:

- Payment abstraction
- Provider integration
- Callback verification
- Idempotency
- Reconciliation

---

## B08 — Content/Search/Discovery

Planned:

- SEO content
- Search contracts
- Filtering
- Public discovery APIs

---

## B09 — Admin Operations

Planned:

- Admin workflows
- Audit logs
- Moderation tools
- Operational controls

---

## B10 — Security & Production Readiness

Planned:

- Security audit
- Rate limits
- Observability
- Backup/restore verification
- Production checklist

---

## Integration and Delivery

After backend phases:

- Frontend integration
- Full acceptance testing
- Server deployment rehearsal
- Production readiness review
- Final delivery

---

## Important Rule

A future chat must continue from this document and the latest Git SHA. Do not restart architecture decisions without reviewing completed phase evidence.
