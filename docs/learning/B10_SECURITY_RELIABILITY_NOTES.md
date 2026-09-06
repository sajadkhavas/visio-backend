# B10 — Security, Reliability & Release Gate — Engineering Notes

## What this phase changed

B10 hardens the accepted backend rather than adding new business domains.

The implementation adds:

- structured request observability with safe request IDs;
- stricter fail-closed production configuration;
- dependency vulnerability auditing in the permanent quality gate;
- explicit CSRF/login-abuse acceptance tests;
- a read-only cross-domain integrity verifier;
- checksum-bearing PostgreSQL backup/restore scripts;
- executable backup → disposable restore → integrity rehearsal in CI;
- deterministic release manifests.

## Security lessons

### Fail closed at process startup

Misconfiguration should fail before traffic reaches the service. Production rejects wildcard hosts, insecure trusted CSRF origins, disabled HTTPS redirect, weak/missing secrets and downgrade-capable PostgreSQL SSL modes.

### Keep Django's security boundary rather than bypassing it

The API continues to use session authentication plus Django CSRF. B10 verified that login without a valid CSRF token is rejected and that the actual scoped login throttle reaches 429 after the configured 10/min budget.

### Security tooling belongs in the gate

A one-off vulnerability scan is weak evidence. The accepted quality workflow now audits the frozen installed environment on every gate and fails on reported vulnerabilities. The accepted implementation head reported no known vulnerabilities across 30 installed packages.

## Reliability lessons

### A dump is not a recovery plan

B10 treats restore evidence as mandatory. The gate creates a custom PostgreSQL dump, verifies its checksum, restores to a disposable database, verifies migration state and runs business-integrity checks on the restored database.

### Recovery verification should understand business truth

Database connectivity alone cannot prove recovery. `verify_business_integrity` checks the accepted B09 audit chain and important order/payment/reconciliation relationships in addition to database constraints.

### Liveness and readiness serve different purposes

`/health/` remains DB-independent so a database outage does not make the process appear dead. `/ready/` actively checks PostgreSQL and returns 503 when the database is unavailable. Existing B00 tests already exercise both behaviors and B10 retains them as release evidence.

## Observability lessons

Structured logs are useful only if they do not become a new data-leak surface. VISIO request logs use method/path/status/duration/request-id and deliberately omit query strings, request bodies and credentials.

Request IDs from clients are accepted only when short and character-bounded; otherwise the backend replaces them.

## Performance lesson

B10 preserves the existing rich catalog query budget and bounded API contracts. It does not create speculative indexes/caches. Real integrated traffic characteristics belong to I00/R00, where PostgreSQL statistics and query plans can justify changes with evidence.

## Release identity

A release manifest is deterministic and includes:

- Git SHA;
- exact Python version;
- `uv.lock` SHA-256;
- hashes of all tracked files.

CI generates the manifest twice and requires byte-for-byte equality.

## Accepted implementation evidence

- START_SHA: `64e2e9580be802977844225c3cbc260520dcb488`
- implementation branch: `phase/visio-b10-security-reliability-release-gate`
- implementation END_SHA: `f1f3d35796aad385372cb3316daad3c2dbf04fb9`
- implementation Gate #388 / run `34034532159` — PASS
- dependency audit: no known vulnerabilities, 30 installed packages checked
- strict mypy: 121 source files PASS
- PostgreSQL suite: 116/116 PASS
- B10 security/reliability tests: 6/6 PASS
- migration drift: 0
- migrate-from-zero PostgreSQL 16.15: PASS
- cross-domain integrity verifier: PASS
- OpenAPI: PASS
- backup/checksum/disposable restore/restored-integrity rehearsal: PASS
- production deployment check: PASS with explicit HSTS includeSubDomains/preload deferral
- deterministic release manifest: PASS
- Ruff, action pins, secret sanity and bytecode compilation: PASS

## What B10 does not prove

B10 does not prove:

- a real production host is configured;
- reverse proxy/TLS/service manager behavior;
- restart/persistence/rollback on the real server;
- frontend-to-backend end-to-end behavior;
- real production traffic performance.

Those claims belong to I00, R00 and S00.
