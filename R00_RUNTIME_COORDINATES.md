# R00 Backend Runtime Coordinates

- R00 backend START: `ab87544cec492a8dee3fb98dba004b5ee122251c`
- runtime hardening candidate before this seal: `f349d224d41021cf8d781731207f03284c891222`
- permanent quality gate on candidate: `34053782084` — PASS
- production server: Gunicorn `26.2.0`
- TLS scheme reconstruction: Django `SECURE_PROXY_SSL_HEADER` from controlled reverse proxy
- real provider credentials: not required or fabricated in R00

This file seals the runtime coordinates for the final exact-head backend R00 PR gate. The exact PR head is the commit containing this file and must be used as the expected merge head after a fresh Backend Quality Gate passes.
