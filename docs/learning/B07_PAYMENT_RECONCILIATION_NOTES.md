# B07 — Payment & Reconciliation — Engineering Notes

## What B07 establishes

Payment is an external-truth integration, not a browser-success flow. The backend records its own attempt state, sends only the server-authoritative amount, treats callback data as untrusted input and asks the provider to verify before changing Order truth.

## Important engineering lessons

### 1. Provider success and Order success are related but not identical

A provider can truthfully report a completed payment while the Order can no longer be safely confirmed because of a cancellation/expiry race, stale reservation or another domain mismatch. Rolling back the local `verified` row in that case would erase evidence of real money movement.

B07 therefore persists provider verification first and performs the Order/inventory transition separately. A mismatch becomes reconciliation evidence rather than fabricated consistency.

### 2. Idempotency must include in-flight states

A unique idempotency key prevents duplicate database rows but does not by itself prevent two concurrent workers from making duplicate outbound provider requests. `requesting` and `verifying` are explicit in-flight states; concurrent retries fail closed until the first operation resolves.

A partial unique PostgreSQL constraint also prevents multiple active/verified attempts for one Order.

### 3. Currency naming and provider units must be explicit

VISIO stores commerce values as integer Toman while canonical currency metadata is IRR. ZarinPal's request/verify amount is IRR, so B07 performs an exact integer `×10` conversion and persists both values. PostgreSQL checks protect the relationship.

### 4. Callback receipt is not payment proof

The callback only supplies an authority/status that helps locate the attempt and decide whether verification should be attempted. Only the provider verification response can produce verified payment truth.

### 5. Reconciliation should expose uncertainty

Operationally dangerous systems often try to make records agree automatically. B07 deliberately records `mismatch` or `provider_error` instead. Later staff tooling can review evidence without losing the original provider/order facts.

### 6. Capability must come from official provider material

Request, verify, reversal and refund behavior were checked against ZarinPal's official Python SDK. Refund support is represented as a gated adapter capability because the official SDK exposes its GraphQL mutation and access-token requirement; B07 does not equate adapter availability with production authorization policy.

## Test strategy

The PostgreSQL suite proves normal success and negative/race conditions, including:

- exact Toman→IRR conversion;
- idempotent payment start;
- duplicate callback safety;
- forged/failed verification cannot confirm an Order;
- non-OK callback does not consume inventory;
- missed callback recovery through reconciliation;
- verified payment after cancelled Order becomes mismatch;
- verified payment survives reservation/inventory transition failure;
- verified amount discrepancy becomes mismatch;
- one active/verified attempt per Order at DB level;
- user-scoped payment detail;
- payments disabled by default;
- official ZarinPal v4/GraphQL endpoint contract.

## Deferred intentionally

- live Merchant ID/access token validation belongs to environment/server phases;
- merchant refund authorization/audit workflow belongs to later admin/security phases;
- HSTS includeSubDomains/preload remain explicitly deferred to R00/S00 under the existing deployment gate policy;
- no additional payment provider is introduced without a new official-reference audit.
