# B03 — Python Learning Notes: Pricing & Inventory Integrity

Date: 2026-09-03

These notes map B03 production code to the Python/Django concepts used to build it. They are educational notes, not a second source of commerce truth; the implementation, migrations, tests and B03 ADR remain authoritative.

## 1. Exact money: `Decimal`, not `float`

Binary floating-point is unsuitable for authoritative money because many decimal values cannot be represented exactly. B03 therefore stores catalog amounts with Django `DecimalField` and uses Python `Decimal` in tests and model-facing code.

B03 freezes catalog amount storage at scale 0 in Toman while retaining ISO currency identity `IRR` and explicit display unit `تومان`. Payment-provider conversion belongs to B07 and must not silently alter B03 catalog truth.

Relevant production model:

- `apps.commerce.models.VariantPrice`
- `amount_toman = DecimalField(max_digits=18, decimal_places=0)`
- optional `compare_at_toman` uses the same exact representation.

Database constraints reject negative current prices and reject a compare-at price that is not strictly greater than the current price.

## 2. Model truth versus derived truth

B03 deliberately does not store every convenient value.

Stored inventory truth:

- `VariantInventory.on_hand`
- `InventoryReservation` rows and their state/expiry.

Derived truth:

- active reserved quantity;
- available-to-promise quantity;
- `in-stock` / `out-of-stock`;
- `maxQuantity`;
- compatibility `inStock`.

Not storing a second mutable `reserved` counter avoids a classic drift problem where a process crash, retry, or expiry update changes reservation rows but fails to update the counter.

## 3. Transactions are a boundary, not a decoration

`transaction.atomic()` means all database work inside the block commits together or rolls back together.

B03 keeps those blocks deliberately short around inventory mutations:

- reserve;
- release;
- consume;
- set on-hand.

The project does not enable global `ATOMIC_REQUESTS` merely to make inventory safe. A narrow transaction reduces lock duration and makes the critical section obvious.

## 4. `select_for_update()` and PostgreSQL row locking

Reading stock and then writing a reservation in separate unprotected steps creates a race:

1. request A sees 5 available;
2. request B also sees 5 available;
3. both reserve 4;
4. the system oversells.

`reserve_variant()` opens a transaction and retrieves the `VariantInventory` row using `select_for_update()`. PostgreSQL then blocks another competing locker/writer for that inventory row until the first transaction finishes. The second request re-evaluates authoritative availability after acquiring the lock.

The acceptance test uses two real Python threads with separate Django database connections against PostgreSQL 16.15. With on-hand 5 and two simultaneous requests for quantity 4, exactly one reservation may succeed.

This is a real concurrency test, not a mock of a lock.

## 5. Lock ordering

When multiple related rows are involved, inconsistent lock order can create deadlocks. B03 transitions first identify the reservation's inventory and then lock the inventory row before locking the reservation row.

Future operations that lock multiple inventory rows must sort their identifiers and acquire locks deterministically.

## 6. Reservation state machine

`InventoryReservation.Status` has four states:

- `active`
- `released`
- `consumed`
- `expired`

Important transition rules:

- release is idempotent for already released/expired holds;
- a consumed hold cannot be released;
- only an active, unexpired hold can be consumed;
- consume decrements `on_hand` exactly once;
- stale active holds are lazily normalized to expired during authoritative inventory mutations.

The service layer raises domain-specific exceptions (`InventoryUnavailableError`, `ReservationStateError`) rather than hiding invalid state transitions.

## 7. Expiry without premature infrastructure

A reservation has `expires_at`. Availability queries ignore expired active holds, and mutation paths normalize stale rows while holding the authoritative inventory lock.

This gives correct stock truth without requiring Redis, Celery, RabbitMQ, or a scheduler merely to make expiry safe. A future worker can improve cleanup latency, but correctness does not depend on it.

## 8. Django migrations and dependency ordering

B03 initially exposed an important migration lesson. `commerce` temporarily had models but no migration. During pytest test-database creation Django treated it as an unmigrated app and attempted to create its tables before the migrated `catalog` app existed. PostgreSQL correctly rejected the foreign key to `catalog_productvariant`.

The fix was not to weaken tests or remove the foreign key. Django 5.2.17 generated:

`apps/commerce/migrations/0001_initial.py`

with dependency:

`("catalog", "0001_initial")`

This makes schema ordering explicit and reproducible. The generated migration was normalized only by Ruff formatting/import ordering before being committed.

## 9. Fail-closed API projection

B02 established catalog identity/presentation authority but deliberately returned non-authoritative pricing and availability sentinels.

B03 replaces those sentinels only when real B03 truth exists:

- active variant price -> authoritative price contract;
- active variant inventory -> authoritative availability;
- missing/inactive price or inventory -> remains non-authoritative/unknown;
- no frontend fixture fallback is used.

The product-level projection comes from the active default variant. Variant payloads retain their own price and inventory projection.

## 10. Compatibility fields must be derived

Legacy frontend fields such as `price`, `originalPrice`, and `inStock` are not stored as separate authority. They are derived from `priceContract` and `availability` so there is only one backend truth.

## 11. What B03 intentionally does not solve

- cart persistence: B04
- checkout repricing, address/shipping validation and final totals: B05
- immutable order monetary snapshots: B06
- provider payment conversion, payment/refund/reconciliation: B07
- background cleanup infrastructure unless a measured need appears later.

## Official references

- Django 5.2 DecimalField: https://docs.djangoproject.com/en/5.2/ref/models/fields/#decimalfield
- Django 5.2 transactions: https://docs.djangoproject.com/en/5.2/topics/db/transactions/
- Django 5.2 `select_for_update()`: https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update
- Django 5.2 constraints: https://docs.djangoproject.com/en/5.2/ref/models/constraints/
- PostgreSQL 16 concurrency control: https://www.postgresql.org/docs/16/mvcc.html
- PostgreSQL 16 transaction isolation: https://www.postgresql.org/docs/16/transaction-iso.html
- PostgreSQL 16 explicit locking: https://www.postgresql.org/docs/16/explicit-locking.html
