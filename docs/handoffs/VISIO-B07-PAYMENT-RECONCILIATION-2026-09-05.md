# VISIO B07 — Payment & Reconciliation — Handoff

## Resume truth

B07 application implementation is complete and implementation-head green. Application closure/freeze, PR merge, post-merge verification and the final registry transition remain required before B08 receives its exact START_SHA.

### Exact coordinates

- exact B07 START_SHA: `1269be71e7abcde4f01700f7809c416cefcc49e2`
- implementation branch: `phase/visio-b07-payment-reconciliation`
- implementation END_SHA: `9470ccd25bafce793c9b6e6e2f6d3309c8c1772e`
- frontend tracker: Issue #55

### Accepted implementation evidence

- implementation Gate #250 / run `33978360189`: PASS
- exact implementation head: `9470ccd25bafce793c9b6e6e2f6d3309c8c1772e`
- PostgreSQL suite: **91/91 PASS**
- strict mypy: PASS / 90 source files
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
7. A real verified provider payment must remain durable even if Order/inventory confirmation fails afterward.
8. Such failures become explicit reconciliation mismatches rather than silent repair or provider-truth rollback.
9. Duplicate callbacks/reconciliation retries cannot consume inventory twice.
10. Production payment remains disabled unless valid environment-only configuration is supplied.
11. Merchant ID/access token must never be committed to Git.
12. Refund/reversal behavior may not exceed capabilities evidenced by current official provider documentation.

## Provider contract

The concrete B07 adapter is ZarinPal based on the current official ZarinPal Python SDK. Live request/verify/reverse use the official `payment.zarinpal.com` v4 routes. Refund uses the official `next.zarinpal.com/api/v4/graphql/` endpoint and requires an access token.

B07 does not expose refund authorization as a public API; later B09/B10 staff/audit/security work must preserve provider evidence and explicit authorization.

## B08 integration boundary

B08 — Content, Search & Public Data APIs — must not alter B07 financial/provider truth. It may consume accepted customer/catalog/public data boundaries but must not add payment shortcuts, client-authoritative totals or payment-provider behavior.

## Final transition rule

Do not start B08 from B07 implementation END_SHA or from the later B07 application merge SHA.

After B07 application closure:

1. exact closure/freeze Gate passes;
2. application PR has zero unresolved blocking review threads;
3. application merges using expected head SHA;
4. post-merge `main` Backend Quality Gate passes;
5. docs-only B07 registry PR records all accepted evidence;
6. registry PR exact-head Gate passes and merges with expected SHA;
7. registry post-merge `main` Gate passes.

Only the resulting final post-merge-green backend `main` SHA is the exact B08 START_SHA and may be registered into frontend Issue #56.
