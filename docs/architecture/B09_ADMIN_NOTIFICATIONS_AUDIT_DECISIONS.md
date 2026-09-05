# B09 — Admin Operations, Notifications & Audit — Architecture Decisions

Date: 2026-09-06

## Coordinates

- phase: `B09 — Admin Operations, Notifications & Audit`
- exact START_SHA: `5e4b71facf5393187b7c15e829fee86395866adb`
- implementation branch: `phase/visio-b09-admin-notifications-audit`
- implementation END_SHA: `561922cb4eb80b9ee7edc68842b6ba92a22cf9f9`
- frontend tracking issue: `#57`
- implementation Gate: `#364` / run `33990690444` — PASS

## Official references re-checked

- Django 5.2 Admin: https://docs.djangoproject.com/en/5.2/ref/contrib/admin/
- Django 5.2 authentication/authorization reference: https://docs.djangoproject.com/en/5.2/ref/contrib/auth/
- Django 5.2 authentication customization and permission model: https://docs.djangoproject.com/en/5.2/topics/auth/customizing/
- Django 5.2 database transactions and `on_commit()`: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- Django 5.2 email API/backends: https://docs.djangoproject.com/en/5.2/topics/email/

## Decision 1 — staff roles are deterministic, code-owned authorization policy

B09 uses Django `Group` and `Permission` as the storage/execution mechanism, but the accepted VISIO role matrix is defined in code rather than hand-edited in production Admin.

`bootstrap_staff_roles` resolves and reconciles the matrix. The Django Admin registration for `Group` is read-only, preventing a convenient UI path from silently redefining production roles. Direct user group/permission assignment is restricted to superusers and is separately audited.

This keeps Django's standard permission model while making the intended business roles reviewable in Git.

## Decision 2 — Admin is an operational UI, not a domain bypass

B09 deliberately avoids generic write access for sensitive truth:

- Order mutations go through the B06 lifecycle service and only expose approved fulfillment transitions.
- Payment attempts are read-only in Admin; B07 provider/reconciliation truth is not editable by staff CRUD.
- Price and inventory mutations go through B03-compatible staff services.
- Inventory reservations are read-only because reservation state is owned by commerce/order workflows.
- Catalog/content mutations are audited.
- Customer addresses are read-only from Admin.

All sensitive Admin mutation entry points require an actual authenticated VISIO `User` with `is_staff=True`; otherwise they fail closed with `PermissionDenied`.

## Decision 3 — privileged operational evidence is append-only and tamper-evident

`AuditEvent` is an append-only hash chain serialized through `AuditChainState`.

Each event records sequence, actor snapshot, action, object coordinates, summary, metadata, previous hash and event hash. Ordinary model update/delete is rejected. `verify_audit_chain` replays and validates the chain so accidental or unauthorized mutation becomes detectable.

This is tamper-evident application evidence, not a claim that the database administrator or infrastructure itself is cryptographically immutable. B10/R00/S00 still own production access, backup and recovery hardening.

## Decision 4 — notification intent is durable inside the business transaction

Notification intent is represented by `NotificationOutbox` and is created in the same database transaction as the authoritative order/payment change.

The external email side effect is not part of financial/order truth. Delivery may be triggered after commit, but an SMTP/provider failure cannot roll back or falsify the already-committed order/payment state.

The outbox has a unique dedupe key and records delivery attempts, so retries do not create a second logical notification for the same event.

## Decision 5 — delivery failure is explicit, retryable and observable

`NotificationDeliveryAttempt` records success/failure per attempt. Outbox state tracks pending/sending/sent/failed, attempt count, availability, last error and sent timestamp.

B09 does not silently swallow provider errors as success. Failure remains visible and retryable while business truth remains intact.

## Decision 6 — production email configuration fails closed

When notifications are enabled in production, configuration rejects development-only email backends and requires an explicit sender/configuration. TLS/SSL contradictions are rejected.

B09 provides an email adapter through Django's documented email backend abstraction. It does not commit provider credentials or invent SMS capability. A real SMS adapter remains future work only when a documented provider and environment configuration are selected.

## Decision 7 — staff API is permission-gated

`GET /api/v1/staff/operations/summary/` is a staff-only operational summary and requires the dedicated operations permission boundary. Authentication alone is insufficient.

The API is operational visibility only; it does not introduce alternate mutation paths around domain services.

## Decision 8 — no queue platform is introduced prematurely

The durable outbox is the accepted boundary. B09 does not introduce Celery, RabbitMQ, Kafka or another distributed worker platform without demonstrated throughput/latency need.

B10 may harden execution/recovery mechanics, and production deployment phases may choose a process model, but the durable database contract is independent of that choice.

## Preserved authority boundaries

1. B01 remains identity/account/address authority.
2. B02/B08 remain catalog/publication/search authority.
3. B03 remains price, inventory and reservation authority.
4. B06 remains order lifecycle authority.
5. B07 remains payment/provider/reconciliation authority.
6. Notification delivery never rewrites domain truth.
7. Staff convenience never authorizes direct database-style bypasses through Admin.

## Out of scope

B09 intentionally does not add:

- production deployment or infrastructure credentials;
- Celery/Kafka/RabbitMQ;
- a real SMS provider without an accepted documented provider;
- editable payment state in Admin;
- frontend/backend integration;
- final security/reliability/release rehearsal, which belongs to B10 and later phases.
