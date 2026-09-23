# VISIO — Merchant Admin Capability Matrix

Date: 2026-09-23  
Stage: **S00-C — Visual & Merchant Admin Recovery**  
Backend source inspected: `sajadkhavas/visio-backend@8f39b3a522ee3a6b19aa4f959f6da5b21ca57288`  
Branch: `phase/visio-s00-real-server-deployment`  
Status: **EVIDENCE-BASED INVENTORY / NO IMPLEMENTATION / REAL VPS UNTOUCHED**

## Status vocabulary

- **EXISTS** — the backend already has the necessary domain model, governance/service boundary, permission enforcement and an adequate reusable contract for this capability.
- **PARTIAL** — major pieces exist, but a safe Merchant Admin contract is incomplete.
- **TECHNICAL-ONLY** — capability exists mainly through Django Admin/superadmin or internal services and is not yet exposed as a merchant-facing staff API.
- **MISSING** — the domain capability itself is not implemented. This does not automatically mean it belongs in S00-C scope.

## 1. Existing authorization and governance baseline

### Code-owned roles — EXISTS

Source: `apps/operations/roles.py`

Existing roles are authoritative and must be reconciled rather than replaced:

- `VISIO Catalog Manager`
- `VISIO Content Editor`
- `VISIO Fulfillment Operator`
- `VISIO Finance Reviewer`
- `VISIO Customer Support`
- `VISIO Operations Admin`

The role matrix uses Django `Group` + `Permission`, is reconciled by
`bootstrap_staff_roles`, and Group definitions are read-only in Django Admin.

### Existing sensitive permission checks — EXISTS

Source: `apps/operations/staff_services.py`

Current explicit service checks include:

- `orders.change_order`
- `commerce.change_variantinventory`
- `commerce.change_variantprice`

Source: `apps/operations/permissions.py`

- staff operations summary requires authenticated + active + staff + `operations.view_auditevent`.

Source: `apps/operations/admin.py`

- notification retry requires `operations.dispatch_notificationoutbox`.

There is no evidence that VISIO relies only on `is_staff=True`; Django permissions are already an accepted security boundary.

### Audit chain — EXISTS

Sources:

- `apps/operations/models.py`
- `apps/operations/audit.py`
- `apps/operations/management/commands/verify_audit_chain.py`
- `apps/operations/management/commands/verify_business_integrity.py`

`AuditEvent` is append-only and hash-chained through `AuditChainState`.
Update/delete is rejected by the model, and integrity is independently verifiable.

## 2. Domain/model inventory

| Domain | Actual models |
|---|---|
| accounts | `User`, `Address` |
| cart | `Cart`, `CartLine`, `WishlistItem` |
| catalog | `Brand`, `Category`, `Product`, `ProductOption`, `ProductOptionValue`, `ProductVariant`, `ProductVariantOption`, `ProductMedia`, `ProductBadge` |
| checkout | `ShippingZone`, `ShippingMethod`, `CheckoutTaxPolicy`, `CheckoutSession`, `CheckoutLine` |
| commerce | `VariantPrice`, `VariantInventory`, `InventoryReservation` |
| content | `ContentEntry`, `SiteConfiguration`, `HomepageBlock`, `ContactMessage` |
| operations | `AuditChainState`, `AuditEvent`, `NotificationOutbox`, `NotificationDeliveryAttempt` |
| orders | `Order`, `OrderLine` |
| payments | `PaymentAttempt`, `PaymentReconciliation` |

No current backend app/model domain was found for Campaigns, a promotion/discount engine, Returns/RMA, redirect management, reporting warehouse, Merchant/Store multi-tenancy or SaaS tenancy.

## 3. Existing HTTP API inventory

Current API namespace is `/api/v1/`.

Existing staff-specific endpoint:

- `GET /api/v1/staff/operations/summary/`

All other current APIs are customer/public/system contracts, including auth/account, catalog, content/site, cart/wishlist, checkout, orders, payments and system status.

There is **no existing staff CRUD/read API surface** for catalog management, price/inventory operations, staff order management, customer management, content management, site configuration, homepage management, contact workflow, shipping/tax configuration, payment review, notification operations or audit browsing.

## 4. Capability matrix

| Capability | Status | Evidence / current boundary | Gap for Merchant Admin |
|---|---|---|---|
| Staff roles / role sync | **EXISTS** | `operations/roles.py`, `bootstrap_staff_roles` | no new role system required |
| Django permission enforcement | **EXISTS** | native `user.has_perm`; `require_staff_permission()`; DRF operations permission | reusable staff API permission helper can be generalized |
| Staff role assignment | **TECHNICAL-ONLY** | `accounts/admin.py`; only superuser may alter groups/direct permissions; assignment changes audited | should remain technical/superadmin, not ordinary Merchant UI |
| Staff session/authentication | **PARTIAL** | existing Django session/CSRF auth works for authenticated users | no dedicated `staff/me` contract exposing staff state, roles and allowed capabilities |
| Operations dashboard summary | **PARTIAL** | `GET /staff/operations/summary/` returns order counts, reconciliation mismatch count, notifications and audit count | only principals with `view_auditevent` can use it; not a general role-aware merchant dashboard |
| Brand/category/product/options/variants | **TECHNICAL-ONLY** | models + audited `AuditedCatalogAdmin`; no delete; public catalog read API | no staff read/write API; mutation/audit logic is embedded in Admin rather than reusable service |
| Product media / badges | **TECHNICAL-ONLY** | catalog models; audited generic catalog admin; Catalog Manager has view/add/change | no merchant API/upload workflow |
| Price management | **PARTIAL** | `set_price_as_staff()` enforces `commerce.change_variantprice`, validation, transaction and audit; Admin calls it | safe staff API missing |
| Inventory management | **PARTIAL** | `set_inventory_as_staff()` + `commerce.services.set_on_hand()`; reservation invariant + audit | safe staff API missing; creation path for a missing inventory row is not provided by `set_inventory_as_staff()` |
| Inventory reservation visibility | **TECHNICAL-ONLY** | read-only Django Admin; Catalog Manager / Operations Admin have view permission | no staff read API |
| Cart/wishlist operational visibility | **TECHNICAL-ONLY** | models registered with default Django Admin | ROLE_MATRIX grants no cart model permissions; no staff API; ordinary merchant workflow should not mutate cart truth |
| Checkout session internals | **MISSING** as merchant surface | customer checkout domain/services exist | no Admin registration, staff API or role permissions; should normally remain workflow-owned rather than editable |
| Shipping zones / methods | **PARTIAL** | real models and server-side shipping resolution exist | no `checkout/admin.py`, no staff API, no role assignment for checkout model permissions |
| Tax policy | **PARTIAL** | `CheckoutTaxPolicy` and authoritative checkout tax calculation exist | no Admin registration, staff API or role assignment |
| Discount engine | **MISSING** | checkout/order have `discount_toman`, but checkout service currently sets `discount_toman = 0` | no promotion/discount rule domain; do not add during S00-C without requirement |
| Customer list/detail | **TECHNICAL-ONLY** | audited `VisioUserAdmin`; Customer Support has `view_user/change_user`; auth privilege fields read-only to non-superusers | no staff customer API; Merchant UI must not expose privilege escalation fields |
| Customer addresses | **TECHNICAL-ONLY** | Address Admin is fully read-only; Customer Support/Operations Admin have `view_address` | no staff read API |
| Order customer APIs | **EXISTS** for customer scope | user-scoped list/detail/create/cancel APIs | not a staff management contract |
| Staff fulfillment | **PARTIAL** | `advance_order_as_staff()` enforces `orders.change_order`, calls domain lifecycle service and audits; Admin only exposes forward controlled actions | staff order list/detail/action API missing |
| Order immutability | **EXISTS** | Order Admin fields read-only; direct save rejected; OrderLine fully read-only; forward lifecycle enforced by domain service | preserve exactly |
| Payment truth / provider verification | **EXISTS** | payment service/provider verification/reconciliation and business integrity checks | Merchant UI must not become payment-authoritative |
| Payment/reconciliation visibility | **TECHNICAL-ONLY** | PaymentAttempt and PaymentReconciliation Admin fully read-only; Finance/Fulfillment/Ops roles have view permissions as defined | read-only staff API missing |
| Manual payment reconciliation action | **MISSING** from staff authorization surface | internal `reconcile_attempt()` exists | no dedicated staff permission/API; not required unless explicitly approved |
| ContentEntry CMS | **TECHNICAL-ONLY** | model + public read API + audited ContentEntry Admin; Content Editor has view/add/change | no staff CMS API; audit mutation currently inside ModelAdmin |
| Content SEO controls | **PARTIAL** | `seo_title`, `seo_description` on ContentEntry; default SEO on SiteConfiguration | no staff API; no product/category/brand SEO fields |
| SiteConfiguration | **TECHNICAL-ONLY** | singleton model + public read API + audited Admin | ROLE_MATRIX currently grants no SiteConfiguration permissions to standard VISIO roles |
| Homepage blocks | **TECHNICAL-ONLY** | model + public read API + audited create/update/delete Admin | ROLE_MATRIX currently grants no HomepageBlock permissions; no staff API |
| Contact-message workflow | **TECHNICAL-ONLY** | public CSRF/rate-limited intake; Admin allows only status mutation and audits it | ROLE_MATRIX currently grants no ContactMessage permissions; no staff API |
| Notifications visibility/retry | **TECHNICAL-ONLY** | outbox/attempt Admin; attempts read-only; retry explicitly checks `dispatch_notificationoutbox` | no staff API for list/detail/retry |
| Audit-event browsing | **TECHNICAL-ONLY** | immutable read-only Admin; Finance/Ops can view; summary count API exists | no staff list/detail API |
| Audit-chain verification | **EXISTS** as operational command/permission | `verify_audit_chain` custom permission + management command | should remain privileged operational capability, not ordinary merchant action |
| Store/business settings | **TECHNICAL-ONLY** | SiteConfiguration fields cover identity/contact/trust/footer/default SEO | role assignment + safe staff API missing |
| Search | **EXISTS** for public catalog/content | backend-authoritative public query logic | no special Merchant search needed beyond module staff endpoints |
| Returns/RMA domain | **MISSING** | no return/refund/RMA model/service found | out of S00-C unless product requirement is added |
| Campaigns | **MISSING** | no campaign domain found | out of scope |
| Reports/BI | **MISSING** as a reporting domain | only small operational summary exists | out of scope unless explicitly required |
| Redirect management | **MISSING** | no redirect model/service found | out of scope |
| Multi-tenant Merchant/Store | **MISSING** and **NOT REQUIRED** | current model graph is single-store VISIO | must not be introduced during S00-C |

## 5. Role matrix reconciliation findings

### VISIO Catalog Manager

Already appropriately owns:

- view/add/change for catalog models;
- view/add/change price;
- view/add/change inventory;
- view reservations.

No replacement role is needed.

### VISIO Content Editor

Currently owns only `ContentEntry` view/add/change.

Gap if the Merchant Admin is expected to let this role manage homepage content:

- `content.view_homepageblock`
- `content.add_homepageblock`
- `content.change_homepageblock`

Do not grant SiteConfiguration automatically; store identity/trust/settings are a broader operations responsibility.

### VISIO Fulfillment Operator

Existing order/payment/notification permissions match the accepted fulfillment boundary.
No reason was found to replace this role.

### VISIO Finance Reviewer

Existing read-only order/payment/audit permissions plus audit-chain verification are coherent.
Do not make payment state editable.

### VISIO Customer Support

Existing User view/change, Address view, Order/OrderLine view and PaymentAttempt view are coherent.

Potential role reconciliation if contact inbox belongs to support:

- `content.view_contactmessage`
- `content.change_contactmessage`

No add/delete permission should be needed because public intake creates messages and Admin already prevents add/delete.

### VISIO Operations Admin

Existing matrix is broad but currently omits I00-era SiteConfiguration/HomepageBlock/ContactMessage and checkout configuration models.

If those capabilities are approved for Merchant Admin, minimal reconciliation should extend this **existing role**, not create a parallel Owner/Manager hierarchy:

Content:
- `content.view_siteconfiguration`
- `content.add_siteconfiguration`
- `content.change_siteconfiguration`
- `content.view_homepageblock`
- `content.add_homepageblock`
- `content.change_homepageblock`
- `content.view_contactmessage`
- `content.change_contactmessage`

Checkout configuration:
- `checkout.view_shippingzone`
- `checkout.add_shippingzone`
- `checkout.change_shippingzone`
- `checkout.view_shippingmethod`
- `checkout.add_shippingmethod`
- `checkout.change_shippingmethod`
- `checkout.view_checkouttaxpolicy`
- `checkout.add_checkouttaxpolicy`
- `checkout.change_checkouttaxpolicy`

Deletion should remain ungranted unless a concrete operational requirement and domain-safe deletion rule are separately accepted.

## 6. Admin governance findings that must be preserved

- Group definitions are code-owned and read-only.
- Non-superusers cannot alter `is_staff`, `is_superuser`, groups or direct permissions.
- User mutation is audited; user deletion is disabled.
- Address is read-only.
- Catalog mutation is audited; generic catalog delete is disabled.
- Price and inventory mutation already cross staff-service boundaries.
- Reservations are read-only.
- Orders cannot be directly edited; only controlled forward fulfillment actions are allowed.
- Payment and reconciliation records are read-only.
- AuditEvent is immutable.
- Notification delivery attempts are immutable.
- Contact sender/message fields are read-only; only workflow status is mutable.
- Site configuration is singleton-style and non-deletable.
- Homepage mutation is audited.
- Provider/payment success remains fail-closed and backend-authoritative.

## 7. Principal gap summary

The backend does **not** need a second governance system.

The dominant S00-C gap is:

> existing Django models + Django permissions + audited/domain services **do not yet have a complete merchant-facing staff API surface and Persian/RTL Merchant UI**.

Two implementation preconditions follow from this inventory:

1. reuse the existing Django Group/Permission/role matrix instead of inventing a second permission vocabulary;
2. extract catalog/content/site/contact mutation governance from ModelAdmin-only code into reusable staff/domain service boundaries before exposing equivalent mutations through Merchant APIs.

## 8. Explicit non-scope

Do not introduce as part of S00-C without a new requirement:

- Owner/Manager role hierarchy;
- custom `product.update`-style permission system parallel to Django permissions;
- Merchant/Store multi-tenancy;
- SaaS tenancy;
- Campaign domain;
- promotion/discount engine;
- Returns/RMA domain;
- reporting warehouse/BI domain;
- SEO redirect manager.

