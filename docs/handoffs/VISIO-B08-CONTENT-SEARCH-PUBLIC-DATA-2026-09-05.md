# VISIO B08 — Content, Search & Public Data APIs — Handoff

## Resume truth

B08 application scope is accepted, merged, frozen and application post-merge green. This docs-only registry transition is the only remaining B08 closure step before B09 receives its exact START_SHA.

## Exact coordinates

- exact B08 START_SHA: `6f921cb0a0dfd4e442a3d195ad70b7dc476cf348`
- implementation branch: `phase/visio-b08-content-search-public-data`
- implementation END_SHA: `c300ea1ef55533a010d98399160d7cdd5093e7f5`
- closure/freeze head: `d49cc5fcddbbdf1369e1c87ae5457e6cd5361ca6`
- freeze ref: `freeze/visio-backend-b08-20260905`
- application PR #16 — MERGED with expected head SHA
- application merge: `8085d050835a429bb5023959a37d9ad66f46ef44`
- frontend tracker: Issue #56

## Accepted evidence

- implementation Gate #289 / run `33981548113` — PASS
- closure / exact-head Gate #297 / run `33981702876` — PASS
- application post-merge Gate #298 / run `33981807980` — PASS
- PostgreSQL suite — **96/96 PASS**
- strict mypy — PASS / 99 source files
- migration drift — 0
- migrate-from-zero PostgreSQL 16.15 — PASS
- OpenAPI — PASS
- production deployment checks — PASS
- secret/action-pin gates — PASS
- unresolved blocking PR threads — 0

## Implemented boundaries

- `apps/content/models.py` — durable public editorial truth and publication constraints
- `apps/content/serializers.py` — frontend-shaped public projection and SEO metadata
- `apps/content/api_views.py` — public list/detail plus bounded search/filter/sort
- `apps/content/pagination.py` — bounded page-size policy
- `apps/content/admin.py` — minimal admin registration
- `apps/content/migrations/0001_initial.py` — Django 5.2.17 generated schema
- `apps/catalog/api_views.py` — backend-authoritative public product `q` search
- `tests/test_b08_content_search.py` — visibility/search/constraint/fail-closed coverage

## Public endpoints

- `GET /api/v1/content/`
- `GET /api/v1/content/{kind}/{slug}/`
- existing `GET /api/v1/catalog/products/` accepts bounded `q`

## Invariants future work must preserve

1. Public content must be published, have `published_at`, and not be future-dated.
2. `(kind, slug)` is the durable content identity boundary.
3. Unknown public search/filter parameters fail closed.
4. Query input and page size remain bounded.
5. Search cannot bypass B02 product publication/media visibility.
6. Search cannot invent or override B03 price/inventory/reservation truth.
7. Search/content work cannot alter B07 provider/payment/reconciliation truth.
8. Frontend local fixtures remain non-authoritative; I00 must replace them with accepted APIs, not retain a production fallback.
9. `search_text` is derived server data. Bulk writes/imports that bypass model `save()` must rebuild it explicitly.
10. SEO title/description are backend public metadata; client values are not production authority.
11. A separate search service requires measured evidence that PostgreSQL-native approaches are insufficient.

## Search evolution rule

Current B08 search stays inside PostgreSQL/Django. If real data and latency measurements require an upgrade, evaluate PostgreSQL full-text search with GIN first, then `pg_trgm` for proven similarity needs. Elasticsearch/OpenSearch requires separate evidence and operational acceptance.

## B09 integration boundary

B09 — Admin Operations, Notifications & Audit — may add staff roles, audited content operations, publication workflows and notifications. It must not weaken B08 visibility/search invariants or B01–B07 authority boundaries.

## Final transition rule

Do not start B09 from the B08 implementation END_SHA or application merge SHA.

1. this docs-only registry PR must be exact-head green;
2. unresolved blocking review threads must be zero;
3. registry PR must merge with expected head SHA;
4. registry post-merge `main` Gate must pass;
5. only that resulting final post-merge-green `main` SHA becomes exact B09 START_SHA;
6. B09 Issue #57 and Master #39 must then be updated before B09 implementation begins.
