# VISIO B02 — Catalog, Taxonomy, Variants & Media Handoff

Date: 2026-09-03

## Resume rule

B02 application implementation is complete on its accepted implementation head. Do not redo B00, B01, or the B02 schema/API design. Resume from the live B02 issue and the exact closure/freeze SHA registered there.

## Immutable B02 coordinates

- START_SHA: `54b59b9826d085c6db7a0ec183f7597d3677e6de`
- implementation END_SHA: `28fd8265c26588224b43c35200c7088b7121b1e0`
- branch: `phase/visio-b02-catalog-taxonomy-variants-media`
- implementation exact-head gate: Backend Quality Gate #84 / run `33781706832` — PASS
- closure/freeze SHA: final branch head containing this handoff and `docs/release/B02_FINAL_REPORT.md`; exact SHA is registered in VISIO issue #49 after closure CI
- freeze ref: `freeze/visio-backend-b02-20260903` after closure CI

## Accepted architecture

Runtime remains:

- Python 3.13.15
- Django 5.2.17 LTS
- Django REST Framework 3.18.0
- PostgreSQL 16.15
- modular monolith

No Redis, queues, search engine, microservice, distributed event architecture, or production storage vendor was introduced in B02.

## Catalog authority now established

B02 backend is authoritative for:

- Brand identity/slug
- Category identity/hierarchy/slug
- Product identity/slug/publication/presentation metadata
- Product option/value metadata
- Variant identity/SKU/option selections
- Product/variant media metadata and ordering
- supported B02 badges

B02 is explicitly NOT authoritative for:

- price/discount/tax — B03
- stock/reservation/availability — B03
- shipping eligibility — B05
- full-text search/ranking — B08

Compatibility price/availability fields in public product responses remain fail-closed sentinels until their owning phases provide truth.

## Public visibility contract

A product is public only when the B02 publication contract is satisfied. Public reads exclude draft/archived/future-dated products, products whose required Brand/Category state is inactive, and products without active public product media.

Frontend fixtures are not production authority.

## Data model summary

- `Brand`
- `Category`
- `Product`
- `ProductOption`
- `ProductOptionValue`
- `ProductVariant`
- `ProductVariantOption`
- `ProductMedia`
- `ProductBadge`

Key database rules include unique slugs, no direct category self-parent, published-at requirement for published products, case-insensitive non-empty SKU uniqueness, at most one default variant per product, option/value identities, variant option uniqueness, and media-position uniqueness.

Cross-table ownership rules are validated explicitly in model logic and tests rather than falsely represented as simple CHECK constraints.

## Migration

Accepted migration:

`apps/catalog/migrations/0001_initial.py`

Generated with Django 5.2.17 after the rejected pre-acceptance SKU candidate was removed. Accepted SKU representation uses one empty state: `""`, not both NULL and blank.

No temporary migration-generator workflow may remain in the accepted closure tree.

## Public APIs

Read-only catalog API under `/api/v1/` provides:

- brands
- categories
- products
- product detail by slug

Allow-listed product filters:

- brand
- category
- material
- shape
- color

Allow-listed ordering:

- default
- name ascending
- name descending

Pagination:

- 24 default
- 48 maximum

Relational serializer access is explicitly optimized with `select_related` / `prefetch_related` and covered by query-count regression tests.

## Exact implementation gate evidence

Backend Quality Gate #84 / `33781706832` on `28fd8265c26588224b43c35200c7088b7121b1e0` passed:

- frozen dependency install
- action-pin validation
- secret sanity
- Ruff format/lint
- strict mypy
- Django checks
- migration drift = 0
- migrate from empty PostgreSQL 16.15
- PostgreSQL-backed tests
- OpenAPI validation
- deployment policy
- bytecode compilation

## Known deferred boundaries

- Real product pricing is intentionally absent until B03.
- Real inventory and purchasability are intentionally absent until B03.
- Shipping and delivery decisions remain B05.
- Search ranking remains B08.
- Production media storage/CDN provider is not frozen in B02.
- Full admin operational policy remains B09.

## NEXT

Only after B02 closure head passes exact-head CI, PR is merged with expected head SHA, and merged `main` passes the permanent Backend Quality Gate:

**B03 — Pricing & Inventory**.

B03 must consume B02 Product/Variant IDs as its identity boundary and add money/inventory truth without rewriting the accepted catalog domain.