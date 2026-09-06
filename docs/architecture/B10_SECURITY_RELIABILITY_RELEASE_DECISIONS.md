# B10 — Security, Reliability & Release Decisions

## Context

B10 is the final backend hardening phase before frontend/backend integration. It starts from the accepted B09 backend main SHA:

`64e2e9580be802977844225c3cbc260520dcb488`

The backend already has accepted identity, catalog, commerce, cart, checkout, orders, payments, content/search and staff/audit/notification authority. B10 therefore hardens the existing modular monolith rather than introducing a new platform or duplicating domain services.

## Threat and reliability model

The acceptance work explicitly covers these failure classes:

1. weak or accidentally permissive production configuration;
2. session/CSRF boundary bypass and login abuse;
3. vulnerable or inconsistent Python dependencies;
4. database loss without a verifiable restore procedure;
5. drift between order, payment, reconciliation and audit truth;
6. operational blind spots caused by unstructured request logs;
7. unreproducible release identification;
8. speculative infrastructure or indexing that creates complexity before measured need.

## Decisions

### Production configuration is fail closed

Production refuses to start with:

- missing or weak Django secret keys;
- missing or wildcard `ALLOWED_HOSTS`;
- plaintext/downgrade-capable PostgreSQL SSL modes;
- insecure trusted CSRF origins;
- disabled HTTPS redirect;
- non-positive HSTS duration;
- unsafe payment or notification configuration already protected by previous phases.

HSTS `includeSubDomains` and preload remain deliberately disabled by default. They are not safe to enable until R00/S00 prove that every relevant production subdomain is HTTPS-only and that preload is an intentional operational commitment.

### Existing session authentication remains authoritative

B10 preserves Django/DRF session authentication and Django CSRF protection. Login and registration remain CSRF-protected and scoped throttles remain active. B10 adds abuse tests instead of replacing this with a new authentication product.

### Request observability is structured and privacy-bounded

A request middleware emits JSON completion/failure events with:

- bounded request ID;
- HTTP method;
- path without query string;
- status code;
- duration;
- exception evidence on failure.

Request bodies, query strings, authorization headers and credentials are not added to the structured request record. Invalid client request IDs are replaced by server-generated IDs.

### Dependency audit is an acceptance gate

The CI environment installs the frozen project lock, then audits the installed environment with pinned `pip-audit==2.10.1` and verifies package compatibility. A known vulnerability makes the gate fail; no vulnerability is ignored merely to obtain a green build.

### Backup evidence must include restore evidence

A backup alone is not treated as recovery proof. The release gate:

1. creates a PostgreSQL 16 custom-format dump;
2. writes and verifies a SHA-256 checksum;
3. creates a disposable database;
4. restores the dump into that target;
5. verifies migration state;
6. runs cross-domain integrity verification against the restored data;
7. removes the disposable database.

The restore script refuses to target the source database.

### Cross-domain integrity is explicitly checkable

`verify_business_integrity` verifies the accepted audit chain and key order/payment/reconciliation invariants without modifying data. This is a release/recovery check, not a replacement for database constraints or domain services.

### Release identity is deterministic

`build_release_manifest.py` produces a deterministic manifest containing the Git SHA, Python patch version, `uv.lock` hash and hashes of tracked files. CI generates it twice and requires byte-for-byte equality.

### Performance hardening remains evidence-driven

Existing API contracts already bound pagination/search input and the catalog suite includes a rich product-list query budget. B10 does not add speculative indexes, caches or a search platform. I00/R00 should measure representative integrated workloads and use PostgreSQL statistics/query plans before approving additional indexes or infrastructure.

### No premature distributed infrastructure

B10 does not add Redis, Celery, RabbitMQ, Kafka, Kubernetes, Elasticsearch/OpenSearch or a separate observability platform. None is required to prove the current backend release contract.

## Accepted implementation evidence

Implementation END_SHA:

`f1f3d35796aad385372cb3316daad3c2dbf04fb9`

Backend Quality Gate #388 / run `34034532159` — PASS:

- Python 3.13.15 / Django 5.2.17 / PostgreSQL 16.15;
- frozen dependency install — PASS;
- dependency vulnerability audit — PASS, no known vulnerabilities found across 30 installed packages;
- package compatibility — PASS;
- immutable GitHub Action pins — PASS;
- secret sanity — PASS;
- Ruff format/lint — PASS;
- strict mypy — PASS, 121 source files;
- Django system checks — PASS;
- migration drift — 0;
- migrate-from-zero — PASS;
- cross-domain integrity verifier — PASS;
- PostgreSQL suite — 116/116 PASS;
- OpenAPI validation — PASS;
- checksum backup + disposable restore + restored integrity verification — PASS;
- production deployment check — PASS with only the explicit HSTS includeSubDomains/preload deferral;
- deterministic release manifest — PASS;
- Python bytecode compilation — PASS.

## Official references re-checked

- Django 5.2 deployment checklist: https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/
- Django 5.2 security: https://docs.djangoproject.com/en/5.2/topics/security/
- Django 5.2 CSRF: https://docs.djangoproject.com/en/5.2/ref/csrf/
- PostgreSQL 16 backup and restore: https://www.postgresql.org/docs/16/backup.html
- PostgreSQL 16 `pg_dump`: https://www.postgresql.org/docs/16/app-pgdump.html
- PostgreSQL 16 monitoring/statistics: https://www.postgresql.org/docs/16/monitoring-stats.html

## Boundary to I00/R00

B10 proves the backend release contract. I00 owns integrated frontend/API truth and R00 owns production-shaped process/proxy/TLS/restart/rollback rehearsal. Neither phase may reinterpret B10 evidence as proof that a real production server has already been deployed.
