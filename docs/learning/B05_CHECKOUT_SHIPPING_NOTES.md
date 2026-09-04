# VISIO B05 — Checkout, Shipping & Delivery Engineering Notes

## Why checkout is a separate authority boundary

A browser cart is intentionally provisional. B04 persists authenticated cart intent, but it does not reserve inventory and its frontend snapshots are never payment/order truth. B05 is the first boundary where the backend must take the user's selected cart, address and shipping method and turn them into a short-lived, server-validated commerce statement.

## Locking strategy

B05 uses short Django `transaction.atomic()` scopes and PostgreSQL row locks for state that participates in a checkout decision. The service locks the user/cart/lines, current price records, destination policy, shipping policy and inventory as required. Variant reservations are acquired in deterministic variant-id order. This keeps concurrent checkouts deterministic and prevents oversell without introducing a distributed lock service.

## Inventory semantics

Normal cart mutations still create no reservation. `create_checkout()` creates B03 `InventoryReservation` records with the accepted reservation TTL. A failed multi-line checkout rolls back the outer transaction, so no partial checkout/reservation set survives. Cancellation/expiry releases or expires reservations. `finalize_checkout()` leaves reservations active for B06; it does not consume stock itself.

## Money semantics

Operational amounts remain integer Toman in `DecimalField(..., decimal_places=0)` storage. The API projects `currency=IRR`, `displayUnit=تومان` and `authority=server-validated`. The browser cannot submit an authoritative subtotal, shipping amount, tax or payable amount.

B05 currently owns no promotion engine, so discount is explicitly zero. Tax is not guessed: an active `CheckoutTaxPolicy` must exist for the destination or checkout fails closed.

## Shipping semantics

No external carrier/provider was invented. B05 stores explicit internal `ShippingZone` and `ShippingMethod` policy. Destination resolution chooses the most specific active country/province/city zone and rejects ambiguous configuration. Shipping methods have explicit flat/free-over rates and optional delivery-day bounds.

## Idempotency

Checkout creation is unique per `(user, idempotency_key)`. Reusing a key with the same logical input returns the same checkout; reusing it with changed input conflicts. Finalization keys are scoped per user rather than globally, so independent customers may legitimately produce the same UUID without creating cross-user coupling.

## Staleness checks

Finalization revalidates the cart revision and line set, current server prices, address snapshot, shipping configuration, tax policy, active reservations and authoritative totals. Any drift fails closed and requires the client to start a fresh checkout validation.

## Database invariants

The database independently enforces expressible invariants, including one non-terminal checkout per user, unique create/finalize idempotency keys per user, monetary non-negativity, payable-component equality, checkout-line quantity bounds and `line_total = unit_price * quantity`.

## Tests worth preserving

The B05 suite covers server-only totals, missing tax policy fail-closed behavior, malicious client money fields, idempotency, cross-user isolation, cancellation/release, stale cart/price/address rejection, expiry, DB constraints and a two-thread PostgreSQL race where two users compete for stock=1 and exactly one checkout can reserve it.
