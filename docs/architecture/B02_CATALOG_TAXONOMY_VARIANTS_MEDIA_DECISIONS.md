# B02 — Catalog, Taxonomy, Variants & Media Decisions

Date: 2026-09-03

Status: **FROZEN FOR B02 IMPLEMENTATION**

B02 START_SHA: `54b59b9826d085c6db7a0ec183f7597d3677e6de`

Branch: `phase/visio-b02-catalog-taxonomy-variants-media`

## Authority boundary

B02 makes the backend authoritative for catalog identity and presentation metadata only.

Authoritative in B02:

- brand identity/name/slug;
- category identity/name/slug/hierarchy;
- product identity/slug/name/publication state;
- product presentation fields: shape, material, color, verified dimensions;
- variant identity/SKU and option combinations;
- product/variant media metadata and ordering;
- non-price badges (`new`, `limited`, `editorial`);
- public visibility and catalog ordering/filtering contracts.

Explicitly **not authoritative in B02**:

- price, discount, tax or currency conversion;
- inventory quantity, stock reservation or availability truth;
- shipping eligibility;
- purchase readiness.

Those stay fail-closed until B03/B05. B02 responses therefore expose the frozen frontend price and availability shapes with `authoritative=false`, `current=null`, `compareAt=null`, `status="unknown"`, and `maxQuantity=null`. Compatibility scalar `price` is `0` and `inStock` is `false`; they are documented sentinels only and are never business truth. The frontend action contract remains non-purchasable until B03 supplies authoritative price and inventory data.

## Frozen frontend compatibility contract

The accepted frontend consumes these product concepts:

- stable string `id` and `slug`;
- `brand` display name;
- category code (`sun-men`, `sun-women`, `opt-men`, `opt-women`, `sport`);
- `source="backend"` and product `authoritative=true` for B02 identity/presentation truth;
- ordered media with id/url/alt/width/height/position and optional variant id;
- shape/material/color;
- dimensions: lens width, bridge width, temple length, frame width;
- option definitions and values;
- variant id/SKU/options/media;
- default variant id;
- badges;
- price/availability envelopes that remain non-authoritative until B03.

B02 must not copy development fixture records into production data. Fixtures remain QA-only.

## Data model

### Brand

UUID primary key, unique stable slug, display name, active flag, sort order, timestamps.

Public catalog excludes inactive brands.

### Category

UUID primary key, unique stable slug, display name, optional self-parent, active flag, sort order, timestamps.

A category cannot parent itself. Recursive cycles are rejected by model validation. Public catalog excludes inactive categories.

Category slugs used by the current frontend are data, not Python enums. The initial integration may use the currently frozen codes, while the database model remains extensible.

### Product

UUID primary key, unique slug, name, protected brand/category relations, publication status (`draft`, `published`, `archived`), nullable `published_at`, presentation fields, nullable positive millimetre dimensions, sort order and timestamps.

A published product requires `published_at`. The public queryset requires:

- `status=published`;
- `published_at <= now`;
- active brand;
- active category;
- at least one active product media record.

This prevents draft/future/unrenderable products from leaking through public APIs.

### Product option definitions

`ProductOption` belongs to a product and owns an ordered key/label. `ProductOptionValue` belongs to an option and owns ordered value/label state.

### Product variant

UUID primary key, product relation, optional SKU, active flag, default flag and sort order.

PostgreSQL enforces case-insensitive SKU uniqueness when SKU is present and at most one default variant per product.

Variant selections are normalized through `ProductVariantOption`, which links a variant to exactly one value for each selected option. Model validation checks that product/option/value ownership matches; cross-table ownership cannot be expressed as a simple relational CHECK constraint and therefore remains covered by application validation plus PostgreSQL foreign keys/uniqueness.

### Media

`ProductMedia` uses Django `FileField` and the configured Storage abstraction. The database stores the file name/path reference; the storage backend owns bytes. No cloud vendor is frozen in B02.

Each media item belongs to a product and may target a variant. It includes alt text, optional width/height, position and active state. Product-level and variant-level position uniqueness are enforced separately with conditional PostgreSQL constraints. Model validation prevents a media variant from belonging to a different product.

B02 uses `FileField`, not `ImageField`, so Pillow is not introduced merely to validate image bytes. Production media processing/CDN policy remains a later infrastructure concern.

### Badges

B02 supports `new`, `limited`, and `editorial`. A sale badge is deliberately not B02 authority because sale semantics depend on B03 pricing.

## Public APIs

Versioned read-only routes:

- `GET /api/v1/catalog/brands/`
- `GET /api/v1/catalog/categories/`
- `GET /api/v1/catalog/products/`
- `GET /api/v1/catalog/products/<slug>/`

Product list query contract mirrors the frozen frontend:

- `brand`: comma-separated display names;
- `category`: category slug;
- `material`: comma-separated values;
- `shape`: exact value;
- `color`: exact value;
- `sort`: `default`, `name-asc`, or `name-desc`;
- `page` / bounded `page_size`.

Unknown filter/sort values fail closed with HTTP 400 instead of being silently interpreted as arbitrary ORM fields.

List/detail querysets explicitly use `select_related` and `prefetch_related`. DRF does not automatically optimize relational serializers, so query-count tests are part of B02 acceptance.

## Pagination

B02 uses a dedicated page-number pagination class. Default page size is 24 and client page size is bounded to 48. This does not change pagination behavior for B01/system endpoints.

## Integrity and indexes

Foreign keys keep Django's default indexes. Additional indexes are added only for actual B02 access paths, especially publication ordering/visibility and stable product ordering.

Database constraints remain the final integrity layer for invariants expressible in one row/relation; recursive category cycles and cross-table ownership are additionally validated in model code and tested.

## Publication semantics

Draft and archived products are never public. Future-dated published records are not public. A product without active media is not public. The API detail endpoint returns 404 for any non-public record to avoid revealing internal publication state.

## Admin boundary

B02 may register models in Django admin for verification and controlled data entry. Final role/permission/admin operations/audit policy remains B09.

## Search boundary

B02 only provides bounded field filters and explicit ordering. Full-text search, relevance scoring, suggestions and ranking stay B08.

## Learning notes to preserve

B02 should document:

- Django relations and reverse relations;
- model validation versus database constraints;
- UUID identifiers;
- queryset filtering and `Q` objects;
- `select_related` versus `prefetch_related`;
- serializers and nested read contracts;
- file/storage abstraction;
- pagination;
- migrations and why schema generation is deterministic.

## Official references

- Django 5.2 model fields and relations: https://docs.djangoproject.com/en/5.2/ref/models/fields/
- Django 5.2 indexes: https://docs.djangoproject.com/en/5.2/ref/models/indexes/
- Django 5.2 file/storage APIs: https://docs.djangoproject.com/en/5.2/ref/files/ and https://docs.djangoproject.com/en/5.2/ref/files/storage/
- Django 5.2 constraints: https://docs.djangoproject.com/en/5.2/ref/models/constraints/
- DRF serializers/relations/filtering/pagination: https://www.django-rest-framework.org/api-guide/
- PostgreSQL 16 constraints: https://www.postgresql.org/docs/16/ddl-constraints.html

## Non-goals

No price or inventory authority, cart, checkout, shipping, orders, payments, full search engine, queue, Redis, microservice split, CDN vendor lock-in, or production object-storage selection is introduced in B02.
