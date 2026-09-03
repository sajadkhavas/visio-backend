# VISIO — Remaining Delivery Roadmap

Updated: 2026-09-03

This file is the backend resume roadmap for all remaining VISIO work. The master tracker is frontend repository Issue #39.

## Accepted history

- F19 — Frontend Finalization: COMPLETED / MERGED / FROZEN
- B00 — Backend Foundation: COMPLETED / MERGED / CLOSED
- B01 — Identity/Auth/Account/Address: COMPLETED / MERGED / CLOSED
- B02 — Catalog/Taxonomy/Variants/Media: COMPLETED / MERGED / CLOSED
- B03 — Pricing/Inventory Integrity: COMPLETED / MERGED / FROZEN / POST-MERGE GREEN

Accepted backend baseline after B03:

`f28da671850879db3d1e1f74263aeb80cac54bdc`

Current phase:

- B04 — Cart & Wishlist Persistence — master Issue #52
- exact B04 START_SHA: `f28da671850879db3d1e1f74263aeb80cac54bdc`
- branch: `phase/visio-b04-cart-wishlist-persistence`
- status: IN PROGRESS

## Mandatory execution rules for every future chat

1. Read Master #39, the current phase issue and this file before changing code.
2. Do not redo already closed phases.
3. Verify current accepted `main` SHA before declaring the next START_SHA.
4. Never change `main` directly. Use a dedicated phase branch from the exact accepted SHA.
5. Re-check current official upstream documentation before making framework/security/provider/operational decisions.
6. Do not invent provider, payment, shipping, infrastructure or production capabilities.
7. Django migrations are generated with the accepted Django runtime; do not hand-write initial migrations merely to save time.
8. PostgreSQL is the authoritative database test target; SQLite success is not release evidence.
9. Do not weaken/delete concurrency, ownership, security or integrity tests to make CI green.
10. Production commerce/account/order/payment truth never falls back to frontend fixtures/localStorage.
11. Temporary write-enabled generator/diagnostic workflows must be removed before implementation acceptance.
12. A phase is not Done until all required implementation/closure exact-head gates pass, blocking review threads are zero, PR merges with expected head SHA, post-merge verification passes, and registry/handoff is updated.
13. Defects discovered in later integration/rehearsal/server phases return to Git and are re-tested; no ad-hoc production source edits.
14. No premature microservices, Kafka, RabbitMQ, Celery, Elasticsearch/OpenSearch, Kubernetes or other distributed infrastructure without a demonstrated requirement.
15. Backend repository may remain public by owner-approved exception, but production credentials/config values remain outside Git and secret-sanity/fail-closed rules remain mandatory.

# Remaining execution order

## B04 — Cart & Wishlist Persistence — Issue #52

Status: **IN PROGRESS**

Owns authenticated cart + wishlist persistence, one active cart per user, variant-based cart lines, deterministic add/update/remove/clear, bounded browser-cart import/merge, wishlist idempotency, ownership isolation and B03 price/availability projection.

Rules:
- cart lines do not become price authority;
- ordinary add-to-cart does not reserve stock;
- browser guest state remains client-local until authenticated import;
- B05 remains final checkout repricing/stock/reservation authority.

Required closure: Django-generated migration, PostgreSQL ownership/uniqueness/concurrency tests, OpenAPI, Ruff/strict mypy/Django/security gates, exact-head CI, report/handoff/freeze, expected-SHA merge, post-merge main Gate.

## B05 — Checkout, Address Validation, Shipping & Delivery — Issue #53

Status: **REGISTERED / WAITING FOR B04**

Owns:
- checkout draft/session lifecycle;
- final server-side cart revalidation/repricing;
- stock revalidation + inventory reservation integration;
- B01 address selection/eligibility;
- shipping method/zone/rate authority;
- delivery eligibility/window contract when justified;
- authoritative subtotal/discount/shipping/tax/payable calculation before order creation;
- idempotent finalize boundary for B06.

Must never trust client totals, shipping cost, price snapshots or availability.

## B06 — Orders & Order Lifecycle — Issue #54

Status: **REGISTERED / WAITING FOR B05**

Owns:
- durable Order + OrderLine truth;
- immutable product/variant/quantity/money snapshots;
- public order identifier policy;
- explicit order lifecycle/state machine;
- idempotent creation from B05 checkout;
- customer order history/detail;
- cancellation eligibility/transitions;
- reservation consume/release handoff.

Payment provider truth remains B07.

## B07 — Payment & Reconciliation — Issue #55

Status: **REGISTERED / WAITING FOR B06**

Owns:
- payment attempt/intent records;
- provider abstraction + official-doc-backed adapter;
- create/redirect/callback/verify lifecycle;
- exact provider-unit conversion from canonical money contract;
- callback verification;
- idempotency and duplicate-callback protection;
- payment state transitions;
- reconciliation/discrepancy evidence;
- refund/reversal policy based only on actual provider capability;
- fail-closed provider configuration.

Never treat redirect/callback parameters alone as proof of payment and never invent unsupported refund/payment automation.

## B08 — Content, Search & Public Data APIs — Issue #56

Status: **REGISTERED / WAITING FOR B07**

Owns:
- backend content required by frozen frontend (guides/magazine/blog/FAQ/public-policy data where applicable);
- search/filter/sort over authoritative catalog/content;
- pagination and public metadata/SEO-supporting API fields;
- production removal of fixture-content authority paths.

Use PostgreSQL-native search first unless measured evidence proves a separate search engine is required.

## B09 — Admin Operations, Notifications & Audit — Issue #57

Status: **REGISTERED / WAITING FOR B08**

Owns:
- production-safe staff/admin workflows across catalog/commerce/orders/payments/content;
- role/permission matrix;
- security/operations audit trail;
- notification abstractions and customer/order/payment notifications;
- staff-only operations with domain-invariant preservation.

Admin actions must use domain rules instead of bypassing them. Notification failure cannot falsify financial/order truth.

## B10 — Backend Security, Reliability & Release Gate — Issue #58

Status: **REGISTERED / WAITING FOR B09**

Owns final backend release hardening:
- security/dependency review;
- auth/session/CSRF/rate-limit review;
- production settings fail-closed checks;
- health/readiness/failure-mode review;
- structured logging/observability contract;
- backup/restore and migration/recovery procedures;
- critical query/performance review;
- reproducible backend release artifact/runbook/freeze.

B10 produces the backend release baseline consumed by I00/R00.

## I00 — Full Frontend ↔ Backend Integration — Issue #59

Status: **REGISTERED / WAITING FOR B10**

Owns integration of F19 frontend with accepted backend truth:
- auth/session/CSRF;
- account/address;
- catalog/content/search;
- price/inventory;
- cart/wishlist;
- checkout/shipping;
- orders;
- payment flow;
- loading/error/retry/empty states;
- SSR/hydration/cache correctness;
- removal of production fixture authority.

Any backend contract defect discovered here returns to backend Git and gates instead of being hidden by frontend workarounds.

## R00 — Pre-Production Release Rehearsal — Issue #60

Status: **REGISTERED / WAITING FOR I00**

Owns production-shaped rehearsal before the real server:
- build exact frontend/backend release artifacts;
- migration rehearsal;
- service startup/readiness/health;
- reverse-proxy/TLS configuration rehearsal;
- backup checksum + disposable restore;
- restart/persistence tests;
- rollback/recovery rehearsal;
- critical E2E customer journeys.

R00 is not permission for ad-hoc live deployment. Rehearsal defects return to Git and exact-head CI.

## S00 — Real Server Deployment & Environment Validation — Issue #61

Status: **REGISTERED / WAITING FOR R00**

Owns:
- real server/runtime provisioning and validation;
- deployment of exact R00-approved SHAs;
- runtime services, reverse proxy, TLS, PostgreSQL and persistent storage;
- production migrations under approved runbook;
- health/readiness/monitoring/backups;
- restart persistence and production smoke testing;
- deployed SHA evidence and rollback validation.

No ad-hoc source edits on the live server. Every code/config defect returns to Git, re-tests and re-freezes.

## D00 — Final Acceptance, Documentation & Handover — Issue #62

Status: **REGISTERED / WAITING FOR S00**

Owns final project acceptance:
- end-to-end production-authoritative customer journeys;
- admin/operations acceptance;
- final security/reliability review;
- exact deployed release manifest;
- architecture/API/deployment/operations/recovery documentation;
- known limitations/deferred backlog;
- final handoff package;
- Master #39 final closure decision.

VISIO must not be marked FINAL / PRODUCTION-ACCEPTED before D00 passes every release-blocking gate.

# Global transition rule

For each phase:

`accepted previous main SHA → declare START_SHA → dedicated branch → official-reference audit → ADR/contracts → implementation → Django migrations → PostgreSQL tests → exact implementation-head Gate → report/handoff/learning notes → exact closure/freeze Gate → PR with zero blocking threads → merge using expected head SHA → post-merge main verification → registry update → next phase START candidate`

## Resume instruction

Current work is **B04 / Issue #52**. Do not start B05 or later early. Resume B04 from branch `phase/visio-b04-cart-wishlist-persistence`, compare it against accepted B03 main `f28da671850879db3d1e1f74263aeb80cac54bdc`, preserve registry commits, then complete B04 under the rules above.