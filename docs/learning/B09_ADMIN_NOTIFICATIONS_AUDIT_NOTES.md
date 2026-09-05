# B09 — Admin Operations, Notifications & Audit — Engineering Notes

## Why this phase exists

B01–B08 established backend truth for identity, catalog, commerce, checkout, orders, payments and public content. Before B09, staff operations were either minimal Django Admin registrations or absent. That is not enough for production operations because generic CRUD can bypass invariants and privileged changes need durable evidence.

B09 turns Django Admin into a constrained operational surface while adding authorization policy, audit evidence and durable notification intent.

## Role and permission model

VISIO staff roles use Django Groups/Permissions, but the accepted matrix is deterministic and defined in `apps/operations/roles.py`.

`bootstrap_staff_roles` can check or reconcile that policy. Group definitions are read-only in Admin so production policy cannot drift through ad-hoc UI edits. Superuser changes to a user's groups or explicit permissions are audited.

## Admin mutation rule

A useful rule from B09 is: **Admin is a caller of domain services, not a replacement for them.**

- Order fulfillment actions call the B06 lifecycle service.
- Price/inventory writes call controlled staff services and preserve B03 reservation rules.
- Payment attempts remain read-only.
- Reservations and customer addresses remain read-only.
- Catalog/content writes emit audit events.
- Sensitive mutation paths fail closed unless `request.user` is a real VISIO staff user.

This pattern should continue in future staff tooling and internal APIs.

## Audit chain

`AuditEvent` is append-only and chained by SHA-256 through a serialized chain state. The event stores an actor email snapshot so evidence remains interpretable even when an account later changes or is removed.

`verify_audit_chain` detects sequence/hash-chain corruption. This provides tamper evidence at the application data layer; it does not replace database access controls, append-only infrastructure logging or backups.

## Durable notification pattern

The important reliability boundary is that the outbox row is created **inside the same transaction as the authoritative domain change**.

Only the external delivery side effect occurs after commit. If SMTP fails, order/payment truth stays committed and the outbox remains available for retry. The dedupe key prevents a retry from creating another logical notification.

This avoids the classic crash window where the business transaction commits but a post-commit callback fails before notification intent is durably recorded.

## Delivery attempts

Each dispatch attempt is recorded separately. A notification can move through pending/sending/sent/failed with attempt count and last-error evidence. Failure is visible rather than silently reported as success.

## Production email boundary

The production settings reject development-only email backends when notifications are enabled and require explicit production sender/configuration. Provider secrets remain environment-only.

B09 intentionally does not invent an SMS provider. A future SMS adapter must be based on current provider documentation and the same durable outbox contract.

## Operational API

B09 exposes:

- `GET /api/v1/staff/operations/summary/`

The endpoint is staff/permission-gated and provides operational visibility without creating a second mutation authority.

## Migration provenance

`apps/operations/migrations/0001_initial.py` was generated using Django 5.2.17. Temporary migration/format/import-fix workflows used during implementation were removed before acceptance.

## Accepted implementation evidence

Implementation END_SHA:

`561922cb4eb80b9ee7edc68842b6ba92a22cf9f9`

Backend Quality Gate #364 / run `33990690444`:

- frozen dependencies — PASS;
- immutable action pins — PASS;
- secret sanity — PASS;
- Ruff format/lint — PASS;
- strict mypy — PASS (`118 source files`);
- Django system checks — PASS;
- migration drift — 0 / PASS;
- migrate-from-zero PostgreSQL 16.15 — PASS;
- PostgreSQL suite — **106/106 PASS**;
- B09 operations tests — **10/10 PASS**;
- OpenAPI validation — PASS;
- production deployment checks — PASS with HSTS includeSubDomains/preload explicitly deferred to R00/S00;
- Python compilation — PASS.

## What B10 should build on

B10 should treat B09's role/audit/outbox contracts as accepted application truth and focus on final security/reliability/release hardening: dependency/security review, auth/session/CSRF/rate limiting, health/readiness/logging, backup/restore/recovery, fail-closed production settings and release runbook evidence.
