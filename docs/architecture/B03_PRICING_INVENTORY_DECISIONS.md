# B03 — Pricing & Inventory Integrity Decisions

Date: 2026-09-03

Status: **FROZEN BEFORE SCHEMA ACCEPTANCE**

B03 START_SHA: `8724f0cbeba928bd6db86c01cb81482553d7d843`

## 1. Accepted upstream boundaries

B03 consumes B02 `Product` / `ProductVariant` identity. It does not create a second product model and does not move frontend fixtures into production authority.

The frozen frontend `MoneyValue` contract contains:

- `amount`
- `currency`
- `displayUnit`

and `hasAuthoritativeMoney()` requires authoritative pricing plus a non-null currency. The frontend finance contract explicitly forbids inventing currency/conversion rules from fixture data.

## 2. Money contract

### Currency identity

VISIO B03 canonical currency identity is ISO 4217 `IRR` (Iranian rial).

### Operational catalog unit

VISIO's customer-facing catalog unit is **Toman**, represented as an integer business unit where:

`1 Toman = 10 IRR`

B03 stores catalog price amounts as integer Toman values using Django `DecimalField(..., decimal_places=0)` / Python `Decimal`. Binary `float` is forbidden for authoritative money.

Fields use explicit `_toman` names so storage semantics cannot be confused with rial-denominated provider APIs.

### Public projection

Authoritative catalog `MoneyValue` is projected as:

- `amount`: integer Toman amount
- `currency`: `IRR`
- `displayUnit`: `تومان`

The `currency` identifies the monetary system; `displayUnit` identifies the unit represented by `amount` in this frozen frontend contract.

### Provider boundary

B03 does not send amounts to payment providers. B07 provider adapters must explicitly convert the B03 amount to the provider-required unit. No provider is allowed to consume a Toman amount merely because `currency=IRR` exists in the public representation.

### Rounding

No fractional Toman is accepted, so no runtime rounding is needed. Any future source with fractional values must be normalized before entering B03 authority and must not silently round inside serializers.

### Tax semantics

B03 price is the authoritative **catalog merchandise price** only. B03 does not infer VAT/tax or shipping. Tax treatment is not declared by catalog price in B03 and must be explicitly resolved by the later checkout/order finance contract before final totals are production-approved.

## 3. Sellable identity

Authoritative price and inventory attach to `ProductVariant`, not directly to `Product`.

A product is commerce-ready only when it has an active default variant carrying authoritative price and inventory. A product with no active default variant remains catalog-visible if B02 allows it, but price/availability fail closed and purchase stays disabled.

This keeps one sellable identity for pricing, stock, reservation, cart lines and later order lines.

## 4. Price model

B03 uses one current `VariantPrice` row per `ProductVariant`.

Fields:

- UUID identity
- one-to-one `variant`
- `amount_toman`
- optional `compare_at_toman`
- `is_active`
- created/updated timestamps

Rules:

- authoritative amount is non-negative integer Toman;
- `compare_at_toman`, when present, must be greater than `amount_toman`;
- sale state is derived from a valid compare-at price, never from an independent sale boolean;
- no scheduled price history is introduced in B03 because there is no demonstrated requirement yet;
- later audit/history requirements belong to B09 or an explicitly registered pricing extension.

## 5. Inventory model

B03 uses one `VariantInventory` row per `ProductVariant`.

Stored state:

- UUID identity
- one-to-one `variant`
- `on_hand`
- `is_active`
- timestamps

`on_hand` is non-negative.

B03 deliberately does **not** store a mutable `reserved` counter. Reserved quantity is derived from active, non-expired `InventoryReservation` rows. This removes a duplicated truth field that could drift from hold rows after crashes or expiry.

Derived at a timestamp `now`:

`reserved = SUM(quantity WHERE status=active AND expires_at>now)`

`available = max(on_hand - reserved, 0)`

A negative derived result is an integrity failure and must never be treated as purchasable.

## 6. Reservation model

`InventoryReservation` fields:

- UUID identity
- FK to `VariantInventory`
- positive integer `quantity`
- status: `active`, `released`, `consumed`, `expired`
- `expires_at`
- created/updated timestamps

Expired active rows are logically non-reserving as soon as `expires_at <= now`. Mutation services may mark them `expired` lazily for state hygiene, but correctness does not depend on a background worker.

This intentionally avoids adding Redis/Celery/RabbitMQ/cron solely to make expiry correct.

## 7. Concurrency and lock order

All authoritative stock mutations use short explicit `transaction.atomic()` blocks.

Reservation creation:

1. lock the target `VariantInventory` row with `select_for_update()`;
2. calculate active non-expired reserved quantity inside that transaction;
3. verify requested quantity <= available;
4. create the reservation;
5. commit.

Because competing reservations for the same variant must acquire the same inventory-row lock, concurrent requests serialize at the authority row and cannot both spend the same available units.

Release/consume lock order is always:

1. identify inventory id using a non-locking lookup;
2. enter `transaction.atomic()`;
3. lock `VariantInventory`;
4. lock `InventoryReservation`;
5. validate transition and mutate.

The consistent Inventory → Reservation lock order is mandatory to reduce deadlock risk.

Transactions must not wait for user input or external network calls.

## 8. Reservation transitions

Allowed authoritative transitions:

- active → released
- active → consumed
- active → expired

Repeated release of an already released/expired reservation is a no-op and must not free stock twice.

Consume of released, expired or already consumed reservation is rejected.

Consume decrements `on_hand` by the reservation quantity in the same transaction in which the reservation becomes consumed.

If an active reservation is already expired when release/consume is attempted, it is normalized to expired first and cannot be consumed.

## 9. Public availability projection

For a variant with active inventory authority:

- available > 0 → `status="in-stock"`
- available == 0 → `status="out-of-stock"`
- `authoritative=true`
- `maxQuantity=available`
- `updatedAt` from inventory authority

Missing/inactive inventory:

- `status="unknown"`
- `authoritative=false`
- `maxQuantity=null`

Product-level availability is derived from the active default variant. No independent product stock boolean is stored.

## 10. Public price projection

Active variant price:

- current MoneyValue from `amount_toman`
- optional compareAt from `compare_at_toman`
- `currency="IRR"`
- `displayUnit="تومان"`
- `authoritative=true`
- `source="backend"`

Missing/inactive price fails closed with authoritative false.

Product-level price is derived from the active default variant. Compatibility `price`, `originalPrice`, and `inStock` are serializer-derived only and are never separately stored.

## 11. Sale badge

A public `sale` badge may be derived when the default variant has active authoritative `compare_at_toman > amount_toman`. It is not persisted as an independent business truth in B03.

## 12. Query strategy

Public catalog querysets must prefetch:

- variant prices
- variant inventory
- active reservation rows needed for current availability projection

Serializers must not perform a query per variant for price/stock state. Query-count regression coverage remains mandatory.

## 13. Testing strategy

Ordinary model/API tests run on PostgreSQL.

Locking/oversell tests must use transaction-capable test semantics (pytest-django `transaction=True` or Django `TransactionTestCase`) rather than relying on `TestCase`'s wrapping transaction, matching Django's `select_for_update()` guidance.

At least one real concurrent reservation test must demonstrate that two requests cannot reserve more than `on_hand`.

## 14. Explicitly deferred

- cart ownership/idempotency — B04
- checkout repricing/final total validation — B05
- order money snapshots / lifecycle — B06
- payment-provider amount conversion — B07
- audit/history/admin workflow — B09
- queue-based expiry optimization — only after measured need

## 15. Official reference baseline

- Django 5.2 DecimalField: https://docs.djangoproject.com/en/5.2/ref/models/fields/#decimalfield
- Django 5.2 transactions: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- Django 5.2 select_for_update: https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update
- Django 5.2 constraints: https://docs.djangoproject.com/en/5.2/ref/models/constraints/
- PostgreSQL 16 concurrency control: https://www.postgresql.org/docs/16/mvcc.html
- PostgreSQL 16 explicit locking: https://www.postgresql.org/docs/16/explicit-locking.html
- PostgreSQL 16 transaction isolation: https://www.postgresql.org/docs/16/transaction-iso.html

B03 implementation must not weaken these frozen truth/concurrency boundaries merely to make tests green.