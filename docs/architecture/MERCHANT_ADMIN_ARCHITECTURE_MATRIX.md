# VISIO — Merchant Admin Architecture Matrix

Date: 2026-09-23  
Stage: **S00-C — Visual & Merchant Admin Recovery**  
Code baseline audited: `8f39b3a522ee3a6b19aa4f959f6da5b21ca57288`  
Capability inventory: `docs/architecture/MERCHANT_ADMIN_CAPABILITY_MATRIX.md`  
Status: **ARCHITECTURE PROPOSAL / NO IMPLEMENTATION / REAL VPS UNTOUCHED**

## 1. Architecture decision

Build a dedicated **merchant-facing Persian/RTL application surface** on top of the current VISIO backend governance.

Do **not** replace Django Admin, Django Group/Permission, existing role definitions, audited staff services, order/payment state machines or backend authority.

Target:

```text
Public VISIO frontend
        |
        | customer/public APIs
        v
Django authoritative backend
        ^
        | /api/v1/staff/*
        |
Merchant Admin UI (/merchant)

Django Admin (/admin/)
= technical/superadmin operational interface
```

The Merchant Admin is a new UX surface, not a second business-rule implementation.

## 2. Technology recommendation

### Merchant frontend

**Use the existing TanStack Start + React + TypeScript frontend repository** and add a separately laid-out route subtree under:

`/merchant`

Reasons:

- VISIO already has an accepted TanStack Start production runtime and release gate;
- Persian RTL/design tokens/components can be reused;
- one deployment/runtime avoids a second frontend supply chain during S00-C;
- route-level separation/code splitting is sufficient because security authority remains server-side;
- Merchant API authorization is enforced by Django, so hiding a route in the browser is never treated as security.

Do not make the public Navbar expose Merchant routes to ordinary customers.

### Backend API namespace

Use the already-established backend convention:

`/api/v1/staff/*`

Do **not** invent a parallel `/api/merchant/*` authority model.

### Authentication

Reuse Django session + CSRF.

Add a staff identity/capability endpoint such as:

`GET /api/v1/staff/me/`

It should expose only the information the UI needs, for example:

- authenticated staff identity;
- active/staff flags;
- code-owned VISIO group names;
- normalized Django permission codenames or server-derived module capabilities.

Frontend capability checks are UX only. Every staff endpoint must enforce the real Django permission again.

## 3. Authorization architecture

### Keep

- Django `Group`
- Django `Permission`
- `ROLE_MATRIX`
- `bootstrap_staff_roles`
- `user.has_perm(...)`
- superuser-only role assignment

### Do not create

- `product.create`
- `order.change_status`
- a second role table
- a second custom ACL database
- Owner/Manager hierarchy without requirement

### Reconcile existing roles only where the inventory proved a gap

Candidate minimal additions are documented in the Capability Matrix:

- HomepageBlock permissions for Content Editor;
- ContactMessage view/change for Customer Support;
- SiteConfiguration/HomepageBlock/ContactMessage and ShippingZone/ShippingMethod/CheckoutTaxPolicy permissions for Operations Admin.

These additions are proposals for the implementation wave, not yet applied.

## 4. Service-boundary architecture

### Already reusable — KEEP

`apps/operations/staff_services.py`

- `advance_order_as_staff()`
- `set_inventory_as_staff()`
- `set_price_as_staff()`
- `require_staff_permission()`

Merchant staff APIs should call these rather than write models directly.

### Must be extracted before equivalent Merchant mutations — REFACTOR

Current audit/governance for several mutations is embedded in Django Admin:

- catalog: `apps/catalog/admin.py`
- content: `apps/content/admin.py`
- account staff mutation: `apps/accounts/admin.py`
- contact workflow: `apps/content/admin.py`
- site configuration: `apps/content/admin.py`
- homepage blocks: `apps/content/admin.py`

For Merchant APIs, create reusable **domain/staff service functions** and make both Django Admin and staff APIs call the same functions.

Preferred ownership:

```text
apps/catalog/staff_services.py
apps/content/staff_services.py
apps/accounts/staff_services.py
apps/checkout/staff_services.py
apps/operations/staff_services.py   # cross-domain operations already here
```

Do not move ordinary domain invariants out of their existing domain services. Staff services should orchestrate:

`permission check -> validation/domain service -> transaction -> audit event`.

## 5. Serializer/API architecture

Public serializers must remain public/read-oriented.

Create separate staff serializers/command serializers instead of exposing unrestricted `ModelSerializer(fields="__all__")`.

Recommended pattern:

```text
apps/<domain>/staff_serializers.py
apps/<domain>/staff_api_views.py
apps/<domain>/staff_api_urls.py
```

or an equivalent clearly-separated package.

Rules:

- explicit writable fields;
- immutable IDs/system fields read-only;
- no role/permission fields in ordinary customer editing;
- money/inventory/order/payment fields never accepted as client authority unless the specific controlled staff service owns that mutation;
- server-side pagination/search/filter for merchant tables;
- API errors remain structured and fail closed.

## 6. Merchant module architecture matrix

| Merchant module | Backend status | Staff API needed | Mutation boundary | Existing role basis | UI decision |
|---|---|---|---|---|---|
| Dashboard | PARTIAL | staff identity + permission-aware summary | read-only | all roles; metrics by permission | **BUILD** |
| Products | TECHNICAL-ONLY | list/detail/create/update | new catalog staff service with audit | Catalog Manager / Operations Admin | **BUILD** |
| Categories | TECHNICAL-ONLY | list/detail/create/update | catalog staff service with audit | Catalog Manager / Operations Admin | **BUILD** |
| Brands | TECHNICAL-ONLY | list/detail/create/update | catalog staff service with audit | Catalog Manager / Operations Admin | **BUILD** |
| Variants/options | TECHNICAL-ONLY | list/detail/create/update | catalog staff service with audit | Catalog Manager / Operations Admin | **BUILD** |
| Media/badges | TECHNICAL-ONLY | list/upload/update | catalog staff service with audit | Catalog Manager / Operations Admin | **BUILD** |
| Pricing | PARTIAL | list/detail/update | existing `set_price_as_staff` | Catalog Manager / Operations Admin | **BUILD** |
| Inventory | PARTIAL | list/detail/update | existing `set_inventory_as_staff`; define safe missing-row creation if actually needed | Catalog Manager / Operations Admin | **BUILD** |
| Reservations | TECHNICAL-ONLY | read list/detail | read-only | Catalog Manager / Operations Admin | **READ-ONLY** |
| Orders | PARTIAL | staff list/detail + controlled transition action | existing `advance_order_as_staff` | Fulfillment / Support read / Finance read / Ops Admin | **BUILD** |
| Customers | TECHNICAL-ONLY | staff list/detail; narrowly-scoped edits only if accepted | account staff service + audit | Customer Support / Ops Admin | **BUILD, LEAST-PRIVILEGE** |
| Addresses | TECHNICAL-ONLY | staff read list/detail | read-only | Customer Support / Ops Admin | **READ-ONLY** |
| CMS content | TECHNICAL-ONLY | staff list/detail/create/update | content staff service + audit | Content Editor / Ops Admin | **BUILD** |
| Homepage | TECHNICAL-ONLY | staff list/detail/create/update/reorder/enable | content staff service + audit | proposed Content Editor / Ops Admin extension | **BUILD** |
| Contact messages | TECHNICAL-ONLY | staff list/detail/status update | content staff service + audit | proposed Support / Ops Admin extension | **BUILD** |
| Store settings | TECHNICAL-ONLY | singleton get/update | content staff service + audit | proposed Ops Admin extension | **BUILD** |
| Shipping zones | PARTIAL | staff list/detail/create/update | checkout staff service + validation/audit | proposed Ops Admin extension | **BUILD** |
| Shipping methods | PARTIAL | staff list/detail/create/update | checkout staff service + validation/audit | proposed Ops Admin extension | **BUILD** |
| Tax policy | PARTIAL | staff list/detail/create/update/activate | checkout staff service + validation/audit | proposed Ops Admin extension | **BUILD** |
| Payments | TECHNICAL-ONLY | staff list/detail | read-only | Finance/Fulfillment/Ops per existing perms | **READ-ONLY** |
| Reconciliation | TECHNICAL-ONLY | staff list/detail | read-only | Finance/Fulfillment/Ops | **READ-ONLY** |
| Notifications | TECHNICAL-ONLY | list/detail + controlled retry | existing notification dispatcher wrapped by permissioned staff service | Fulfillment/Ops | **BUILD** |
| Audit | TECHNICAL-ONLY | list/detail filters | immutable read-only | Finance/Ops | **READ-ONLY** |
| Cart/wishlist | TECHNICAL-ONLY | optional troubleshooting read endpoints | no merchant mutation | no existing ordinary role assignment | **DEFER unless acceptance requires** |
| Checkout sessions | no merchant surface | optional troubleshooting only | workflow-owned; no direct edit | none | **DEFER** |
| Discounts/Campaigns | MISSING | none | no domain | none | **DO NOT BUILD** |
| Returns/RMA | MISSING | none | no domain | none | **DO NOT BUILD** |
| Reports/BI | MISSING | none | no reporting domain | none | **DO NOT BUILD** |
| Redirect manager | MISSING | none | no domain | none | **DO NOT BUILD** |
| Multi-tenant Store | MISSING / not required | none | single-store architecture remains | none | **DO NOT BUILD** |

## 7. Recommended Merchant route matrix

Frontend routes, subject to backend permission guards:

```text
/merchant
/merchant/products
/merchant/products/$id
/merchant/categories
/merchant/brands
/merchant/inventory
/merchant/orders
/merchant/orders/$id
/merchant/customers
/merchant/customers/$id
/merchant/content
/merchant/content/$id
/merchant/homepage
/merchant/messages
/merchant/settings/store
/merchant/settings/shipping
/merchant/settings/tax
/merchant/payments
/merchant/payments/$id
/merchant/notifications
/merchant/audit
```

Do not create routes for campaigns, returns, BI reports, redirects or stores/tenants.

A route may exist in code but must render/redirect based on server-reported staff capability. The backend remains the actual authorization boundary.

## 8. Recommended staff API matrix

Proposed namespace only; no endpoint is implemented by this document.

```text
GET    /api/v1/staff/me/

GET    /api/v1/staff/catalog/products/
POST   /api/v1/staff/catalog/products/
GET    /api/v1/staff/catalog/products/{id}/
PATCH  /api/v1/staff/catalog/products/{id}/
...categories / brands / options / variants / media / badges

GET    /api/v1/staff/commerce/prices/
PATCH  /api/v1/staff/commerce/prices/{variant_id}/
GET    /api/v1/staff/commerce/inventory/
PATCH  /api/v1/staff/commerce/inventory/{variant_id}/
GET    /api/v1/staff/commerce/reservations/

GET    /api/v1/staff/orders/
GET    /api/v1/staff/orders/{id}/
POST   /api/v1/staff/orders/{id}/advance/

GET    /api/v1/staff/customers/
GET    /api/v1/staff/customers/{id}/
GET    /api/v1/staff/customers/{id}/addresses/

GET/POST/PATCH /api/v1/staff/content/...
GET/POST/PATCH /api/v1/staff/homepage/...
GET/PATCH      /api/v1/staff/site/config/
GET/PATCH      /api/v1/staff/contact/messages/...

GET/POST/PATCH /api/v1/staff/shipping/zones/...
GET/POST/PATCH /api/v1/staff/shipping/methods/...
GET/POST/PATCH /api/v1/staff/tax/policies/...

GET    /api/v1/staff/payments/
GET    /api/v1/staff/payments/{id}/
GET    /api/v1/staff/reconciliations/

GET    /api/v1/staff/notifications/
POST   /api/v1/staff/notifications/{id}/retry/

GET    /api/v1/staff/audit/
GET    /api/v1/staff/audit/{id}/

GET    /api/v1/staff/operations/summary/   # existing
```

Exact resource shapes should be finalized per implementation wave from current models/services, not guessed globally.

## 9. Django Admin role after Merchant Admin exists

Canonical route remains:

`/admin/`

Purpose:

- technical/superadmin operational interface;
- emergency and low-level model visibility;
- code-owned role assignment by superuser;
- immutable audit/payment evidence inspection;
- fallback operational access.

It is **not** the migration UI, debugging environment or a database shell.

Django migrations, diagnostics and server operations remain CLI/release-runbook responsibilities.

## 10. Security rules

1. Merchant route visibility is never authorization.
2. Every staff API enforces native Django permissions.
3. Every sensitive mutation uses the accepted domain/staff service boundary.
4. Payment/provider truth stays read-only to Merchant UI unless a separately approved controlled operation exists.
5. Orders remain state-machine controlled; no generic status PATCH.
6. Inventory cannot be set below active reservations.
7. Price validation remains server-side.
8. Audit evidence remains append-only.
9. Role definitions remain code-owned.
10. No direct frontend-to-database or frontend-to-Django-Admin automation.
11. CSRF/session policy stays consistent with the accepted B10/I00 boundary.
12. No fake operational success and no fixture business truth.

## 11. Suggested implementation waves after explicit approval

### MA-0 — Staff contract foundation

- `staff/me`;
- reusable Django permission helper for staff APIs;
- role-matrix reconciliation limited to proven gaps;
- extract audited catalog/content/site/contact staff services;
- add checkout configuration staff services;
- tests proving Admin and staff API use the same governance boundary.

### MA-1 — Merchant shell

- `/merchant` RTL layout;
- staff session guard;
- permission-driven navigation;
- accessible desktop/mobile shell;
- dashboard using existing operations summary where permitted.

### MA-2 — Catalog + Commerce

- products/categories/brands/variants/options/media;
- price/inventory;
- reservation read-only;
- audited mutations and browser acceptance.

### MA-3 — Orders + Customers

- staff order lists/details;
- controlled fulfillment action;
- customer/address read surfaces;
- no privilege escalation.

### MA-4 — Content + Homepage + Contact + Store Settings

- CMS;
- homepage;
- contact workflow;
- SiteConfiguration;
- preserve public frontend authority.

### MA-5 — Shipping/Tax + Financial/Operational visibility

- shipping zones/methods;
- tax policy;
- payment/reconciliation read-only;
- notification retry;
- audit read-only.

After each wave:

- backend Ruff/mypy/pytest/schema/security checks as applicable;
- frontend typecheck/lint/production build;
- targeted browser tests.

After all waves:

- rerun S00 production-shaped local gate;
- persistent local QA;
- Merchant Admin manual acceptance;
- public visual acceptance;
- only then reconsider real VPS entry.

## 12. Final recommendation

The correct architecture is **not** a new admin backend.

It is:

**Existing Django domain models + existing native permissions/roles + existing business services/audit + a new permissioned staff API layer + a professional Persian/RTL TanStack Merchant UI.**

This preserves the accepted backend governance and concentrates S00-C work on the actual missing product layer.
