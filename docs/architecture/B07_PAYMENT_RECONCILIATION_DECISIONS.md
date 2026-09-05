# VISIO B07 — Payment & Reconciliation Decisions

Date: 2026-09-05

## Coordinates

- exact START_SHA: `1269be71e7abcde4f01700f7809c416cefcc49e2`
- implementation branch: `phase/visio-b07-payment-reconciliation`
- tracker: frontend/master Issue #55

## Official references re-checked

Payment-provider behavior was checked against the current official ZarinPal Python SDK maintained by ZarinPal:

- SDK root: https://github.com/ZarinPal/Zarinpal-Python-Sdk
- payment request implementation: `src/zarinpal-py-sdk/resources/Payments.py`
- verification implementation: `src/zarinpal-py-sdk/resources/Verifications.py`
- reversal implementation: `src/zarinpal-py-sdk/resources/Reverses.py`
- refund implementation: `src/zarinpal-py-sdk/resources/Refunds.py`
- provider base URLs/client configuration: `src/zarinpal-py-sdk/zarinpal.py`

The accepted contract is:

- live REST base: `https://payment.zarinpal.com`
- sandbox REST base: `https://sandbox.zarinpal.com`
- payment request: `/pg/v4/payment/request.json`
- payment verification: `/pg/v4/payment/verify.json`
- reversal: `/pg/v4/payment/reverse.json`
- payment redirect: `/pg/StartPay/{authority}`
- refund: official GraphQL endpoint `https://next.zarinpal.com/api/v4/graphql/`, requiring an access token
- provider request/verify amounts are IRR; the official SDK validates a minimum of 1,000 IRR

No provider capability is inferred from third-party examples.

## Authority boundary

B07 owns payment-provider truth. B06 remains the durable order/lifecycle authority.

A browser redirect, callback query string, customer request or frontend state is never payment proof. An Order may transition from `pending_payment` to `confirmed` only after the backend calls the provider verification operation with the server-stored authority and the exact server-authoritative IRR amount.

Callback `Status=OK` is only a trigger to verify. A non-OK callback never consumes inventory or confirms an order.

## Durable payment model

`PaymentAttempt` stores the payment lifecycle independently from the immutable B06 order snapshot:

- UUID primary key;
- Order foreign key;
- Order-scoped UUID idempotency key;
- provider;
- lifecycle state;
- authoritative amount in both integer Toman and exact IRR conversion;
- provider authority and redirect URL;
- provider code/message/reference ID;
- masked card/card hash evidence when returned;
- request/callback/verify counters;
- verification and state timestamps.

`PaymentReconciliation` stores matched, mismatched and provider-error evidence without rewriting historical provider truth.

## Lifecycle and idempotency

Payment attempt states are:

- `new`
- `requesting`
- `pending`
- `verifying`
- `verified`
- `failed`
- `cancelled`
- `expired`

Database and service invariants enforce:

1. `(order, idempotency_key)` is unique;
2. `(provider, provider_authority)` is unique once an authority exists;
3. at most one `requesting|pending|verifying|verified` attempt may exist per Order;
4. a replay with the same successful idempotency key returns the existing attempt;
5. a request already in `requesting` fails closed instead of issuing a second outbound provider request;
6. a verification already in `verifying` fails closed instead of issuing a second concurrent verification;
7. duplicate callbacks after verification cannot duplicate order/inventory effects.

## Money contract

B03/B05/B06 keep canonical commerce amounts as integer Toman. ZarinPal's provider contract uses IRR.

B07 performs exactly:

`amount_rial = amount_toman * 10`

The conversion is stored, sent to the provider and enforced by a PostgreSQL check constraint. `currency_code` remains `IRR`, while `display_unit` remains `تومان`. Floats are not used for financial values.

Provider verification always receives the originally persisted attempt amount. Reconciliation separately checks that the attempt amount still matches the immutable server-side Order truth before Order confirmation.

## Provider truth vs Order truth

A successful provider verification is durable financial truth and must not be rolled back merely because a later Order/inventory transition fails.

B07 therefore commits verified provider evidence first. It then attempts the B06 payment-confirm transition in a separate transaction.

If Order state, amount, reservation or inventory no longer permits confirmation:

- `PaymentAttempt` remains `verified`;
- Order is not falsely advanced;
- no silent repair occurs;
- a `PaymentReconciliation(status=mismatch)` record is created for explicit operational handling.

This covers races such as payment verified after cancellation/expiry, reservation state failure and server-side amount discrepancy.

## Reconciliation

`reconcile_attempt()` reuses the authoritative provider verification path and is the recovery mechanism for missed callbacks and retryable uncertainty.

Reconciliation results are explicit:

- `matched` — provider verification and server Order truth agree and Order confirmation succeeds;
- `mismatch` — real verified payment exists but Order/inventory/amount truth cannot be safely reconciled automatically;
- `provider_error` — provider verification could not establish success.

No reconciliation path silently changes an amount or fabricates provider success.

## Refund and reversal policy

The provider adapter contains reversal and refund capabilities only because the current official SDK exposes them.

- reversal uses the official v4 REST reversal endpoint and merchant identity;
- refund uses the official GraphQL mutation and requires `ZARINPAL_ACCESS_TOKEN`;
- absence of an access token causes refund to fail closed;
- B07 does not expose an unaudited public refund endpoint or claim that production refund automation is active merely because an adapter method exists.

Operational/admin refund authorization remains outside B07 and belongs to later staff/audit work (B09/B10) unless explicitly accepted earlier.

## Configuration and secret boundary

Payments are fail-closed by default:

- `PAYMENTS_ENABLED=0`
- `PAYMENT_PROVIDER=disabled`
- no Merchant ID or access token is committed to Git.

When production payments are enabled, settings require:

- provider `zarinpal`;
- non-empty `ZARINPAL_MERCHANT_ID`;
- absolute HTTPS callback URL;
- sandbox disabled in production.

`ZARINPAL_ACCESS_TOKEN` remains optional for normal payment request/verification and required only for the official refund API.

## Public API

B07 exposes:

- `POST /api/v1/payments/` — authenticated payment creation/idempotent replay for the caller's pending Order;
- `GET /api/v1/payments/{attempt_id}/` — authenticated user-scoped payment detail;
- `GET /api/v1/payments/zarinpal/callback/` — provider redirect/callback receiver that still requires server-side verification.

Cross-user reads fail closed.

## Non-goals

- storing live provider credentials in Git;
- trusting client totals or callback status as payment truth;
- automatic refund authorization/admin policy — B09/B10;
- background payment microservices, event buses or additional queues without demonstrated need;
- content/search/public-data APIs — B08.
