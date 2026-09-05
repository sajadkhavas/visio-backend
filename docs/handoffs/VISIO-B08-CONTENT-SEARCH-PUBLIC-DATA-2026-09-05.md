# VISIO B08 — Content, Search & Public Data APIs — Handoff

## Resume truth

B08 application implementation is complete and implementation-head green. Closure/freeze, final PR acceptance, merge/post-merge verification and the separate registry transition remain required before B09 receives its exact START_SHA.

## Exact coordinates

- exact B08 START_SHA: `6f921cb0a0dfd4e442a3d195ad70b7dc476cf348`
- implementation branch: `phase/visio-b08-content-search-public-data`
- implementation END_SHA: `c300ea1ef55533a010d98399160d7cdd5093e7f5`
- frontend tracker: Issue #56
- draft application PR: #16

## Accepted implementation evidence

- Backend Quality Gate run `33981548113` — PASS
- PostgreSQL suite — **96/96 PASS**
- strict mypy — PASS / 99 source files
- migration drift — 0
- migrate-from-zero PostgreSQL 16.15 — PASS
- OpenAPI — PASS
- production deployment checks — PASS
- secret/action-pin checks — PASS

## Implemented boundaries

- `apps/content/models.py` — durable public editorial truth and publication constraints
- `apps/content/serializers.py` — frontend-shaped public projection and SEO metadata
- `apps/content/api_views.py` — public list/detail, bounded search/filter/sort
- `apps/content/pagination.py` — bounded page-size policy
- `apps/content/admin.py` — minimal admin registration
- `apps/content/migrations/0001_initial.py` — Django 5.2.17 generated schema
- `apps/catalog/api_views.py` — backend-authoritative public product `q` search
- `tests/test_b08_content_search.py` — visibility/search/constraint/fail-closed coverage

## Public endpoints

- `GET /api/v1/content/`
- `GET /api/v1/content/{kind}/{slug}/`
- existing `GET /api/v1/catalog/products/` now accepts bounded `q`

## Invariants future work must preserve

1. Public content must be published, have `published_at`, and not be future-dated.
2. `(kind, slug)` is the durable content identity boundary.
3. Unknown public search/filter parameters fail closed.
4. Query input is bounded; page size is bounded.
5. Search cannot bypass B02 product publication/media visibility.
6. Search cannot invent or override B03 price/inventory/reservation truth.
7. Search/content work cannot alter B07 provider/payment/reconciliation truth.
8. Frontend local fixtures remain non-authoritative; I00 must replace them with accepted APIs rather than treating them as a fallback in production.
9. `search_text` is derived server data. Bulk writes/imports that bypass model `save()` must rebuild it explicitly.
10. SEO title/description are backend public metadata; client values are not production authority.
11. A separate search service must not be introduced without measured evidence that PostgreSQL-native approaches are insufficient.

## Search evolution rule

Current B08 search intentionally stays inside PostgreSQL/Django. If real data and latency measurements require an upgrade, evaluate PostgreSQL full-text search and GIN first, then `pg_trgm` for proven similarity needs. Elasticsearch/OpenSearch requires separate measured justification and operational acceptance.

## B09 integration boundary

B09 — Admin Operations, Notifications & Audit — may add staff roles, audited content operations, publication workflows and notifications. It must not weaken B08 public visibility/search invariants or B02/B03/B07 authority boundaries.

## Final transition rule

Do not start B09 from the implementation END_SHA or from the later B08 application merge SHA.

After B08 application closure:

1. exact closure/freeze Gate passes;
2. PR #16 is ready and has zero unresolved blocking review threads;
3. application merges with expected head SHA;
4. post-merge `main` quality Gate passes;
5. docs-only B08 registry PR records all accepted evidence;
6. registry PR exact-head Gate passes and merges with expected SHA;
7. registry post-merge `main` Gate passes.

Only the resulting final post-merge-green backend `main` SHA is the exact B09 START_SHA and may be registered into frontend Issue #57.
