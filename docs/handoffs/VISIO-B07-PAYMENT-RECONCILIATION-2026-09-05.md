# VISIO B07 — Payment & Reconciliation — Handoff

## Resume truth

B07 application scope is **COMPLETED / MERGED / FROZEN / APPLICATION POST-MERGE GREEN**. This docs-only registry transition is the final B07 bookkeeping step before B08 receives its exact accepted backend START_SHA.

### Exact coordinates

- exact B07 START_SHA: `1269be71e7abcde4f01700f7809c416cefcc49e2`
- implementation branch: `phase/visio-b07-payment-reconciliation`
- implementation END_SHA: `9470ccd25bafce793c9b6e6e2f6d3309c8c1772e`
- closure/freeze head: `b2230b696c7e587dbaf08d4dc80d3d6a47718b28`
- freeze ref: `freeze/visio-backend-b07-20260905`
- application PR: #14
- accepted application merge: `b7dd550c1bf7e6a543f8a7f348dd8ddc73669c6a`
- frontend tracker: Issue #55

### Accepted application evidence

- implementation Gate #250 / run `33978360189`: PASS
- closure Gate #254 / run `33978559625`: PASS
- PR exact-head Gate #255 / run `33978620868`: PASS
- application post-merge Gate #256 / run `33978686790`: PASS
- unresolved PR review threads: 0
- PostgreSQL suite: **91/91 PASS**
- strict mypy: PASS / 90 source files at implementation Gate
- migration drift: 0
- migrate-from-zero PostgreSQL 16.15: PASS
- OpenAPI: PASS
- production deployment checks: PASS
- secret/action-pin gates: PASS

## Implemented files and boundaries

- `apps/payments/models.py` — durable attempt/reconciliation truth and DB invariants
- `apps/payments/services.py` — start, callback, verify, mismatch-safe confirmation and reconciliation
- `apps/payments/providers/base.py` — provider contract
- `apps/payments/providers/zarinpal.py` — official-contract ZarinPal adapter
- `apps/payments/selectors.py` — user-scoped reads
- `apps/payments/serializers.py` — request/response projection
- `apps/payments/api_views.py` / `api_urls.py` — payment API and callback receiver
- `apps/payments/migrations/0001_initial.py` — Django-generated initial payment schema
- `apps/payments/migrations/0002_paymentattempt_payments_one_active_attempt_per_order.py` — Django-generated active-attempt invariant
- `tests/test_b07_payments.py` — lifecycle/idempotency/security coverage
- `tests/test_b07_hardening.py` — provider-contract, mismatch and DB-hardening coverage

## Invariants future work must preserve

1. Callback/redirect parameters are never payment proof.
2. Only authoritative provider verification may establish `verified` payment truth.
3. Order confirmation uses the server-stored provider authority and exact persisted IRR amount.
4. Toman→IRR conversion is exact integer `×10` and DB-protected.
5. One Order cannot have multiple active/verified payment attempts.
6. Same-key replay is idempotent; in-flight requesting/verifying fails closed against duplicate outbound effects.
7. A real verified provider payment remains durable if Order/inventory confirmation later fails.
8. Such failures become explicit reconciliation mismatches rather than silent repair or provider-truth rollback.
9. Duplicate callbacks/reconciliation retries cannot consume inventory twice.
10. Production payment remains disabled unless valid environment-only configuration is supplied.
11. Merchant ID/access token must never be committed to Git.
12. Refund/reversal behavior may not exceed capabilities evidenced by current official provider documentation.

## Provider contract

The concrete B07 adapter is ZarinPal based on the current official ZarinPal Python SDK. Live request/verify/reverse use the official `payment.zarinpal.com` v4 routes. Refund uses the official `next.zarinpal.com/api/v4/graphql/` endpoint and requires an access token.

B07 does not expose refund authorization as a public API; later B09/B10 staff/audit/security work must preserve provider evidence and explicit authorization.

## B08 integration boundary

B08 — Content, Search & Public Data APIs — must not alter B07 financial/provider truth. It may consume accepted customer/catalog/public-data boundaries but must not add payment shortcuts, client-authoritative totals or new payment-provider behavior.

## B08 START_SHA rule

Do not start B08 from B07 implementation END_SHA or from the B07 application merge SHA.

The exact B08 START_SHA becomes the resulting backend `main` SHA only after this docs-only registry branch:

1. passes its exact-head Backend Quality Gate;
2. has zero unresolved blocking PR review threads;
3. merges with its expected head SHA;
4. passes the post-merge `main` Backend Quality Gate.

Only that final post-merge-green SHA may be registered into frontend Issue #56 and used to create the dedicated B08 branch.
