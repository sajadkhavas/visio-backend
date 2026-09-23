# VISIO S00-C — MA-0 Source Lock

Date: 2026-09-23  
Phase: **S00-C — Visual & Merchant Admin Recovery**  
Subphase: **MA-0 — Staff Contract Foundation**  
Status: **SOURCE LOCKED / IMPLEMENTATION NOT STARTED / REAL VPS UNTOUCHED**

## Exact pre-implementation source coordinates

Frontend repository:

`sajadkhavas/remix-of-remix-of-visionary-designs`

Branch:

`phase/visio-s00-real-server-deployment`

Exact HEAD at MA-0 source lock:

`7ac9833d33d02f49d724f7019776d05e7a62bd5b`

Commit message:

`docs(S00-C): add visual reconciliation matrix`

Backend repository:

`sajadkhavas/visio-backend`

Branch:

`phase/visio-s00-real-server-deployment`

Exact HEAD at MA-0 source lock:

`0b2c15b1fa7ec6248c9ae2875ee9d4fecf5c24e8`

Commit message:

`docs(S00-C): define merchant admin architecture matrix`

## MA-0 implementation scope

MA-0 is intentionally split into six independent evidence checkpoints:

1. `staff/me`
2. reusable staff permission helper
3. minimal existing Role Matrix reconciliation
4. audited Catalog/Content/Site/Contact staff service extraction
5. Shipping/Tax safe staff services
6. tests proving Django Admin and Staff API share the same governance boundary

Each checkpoint must receive its own exact commit/evidence registration before continuing.

## Architecture constraints

- Existing Django `Group` / `Permission` and `apps/operations/roles.py` remain authoritative.
- Do not introduce Owner/Manager replacement roles.
- Do not create a parallel custom ACL/permission vocabulary.
- Do not introduce multi-tenancy, Merchant/Store abstraction, Campaigns, Returns/RMA, BI Reports, Redirects or a discount engine.
- Sensitive mutations must remain behind the accepted domain/staff service boundaries.
- Django Admin remains technical/superadmin operational UI at canonical `/admin/`.
- The Merchant surface will be permissioned through backend staff APIs; frontend route visibility is never authorization.
- No VPS mutation or deployment is allowed during MA-0.

## Existing evidence used as architecture authority

- `docs/architecture/MERCHANT_ADMIN_CAPABILITY_MATRIX.md`
- `docs/architecture/MERCHANT_ADMIN_ARCHITECTURE_MATRIX.md`
- `apps/operations/roles.py`
- `apps/operations/permissions.py`
- `apps/operations/staff_services.py`
- `apps/operations/audit.py`
- B09/B10/I00 accepted tests and architecture documents

## Exit condition

MA-0 is complete only when all six checkpoints are implemented, tested, recorded with exact commit coordinates, and no accepted backend governance invariant is bypassed.
