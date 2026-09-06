# R00 Production Runtime Boundary

Status: R00 backend production-runtime hardening candidate.

## Starting point

- R00 backend START: `ab87544cec492a8dee3fb98dba004b5ee122251c`
- branch: `phase/visio-r00-preproduction-rehearsal`

## Changes owned by R00

1. Replace Django development `runserver` as the deployment runtime with pinned Gunicorn `26.2.0`.
2. Provide `scripts/start_production.sh` as the production WSGI launcher. Invoke it with `bash scripts/start_production.sh`; repository file-mode is not part of this contract.
3. Preserve production fail-closed settings and explicitly trust `X-Forwarded-Proto=https` from the controlled TLS reverse proxy through Django `SECURE_PROXY_SSL_HEADER`.
4. Keep Gunicorn bound to loopback by default. The public edge must be the only externally reachable HTTP/TLS listener.
5. Keep payment and notification providers fail-closed unless real deployment environment values are explicitly configured later.

## Rehearsal topology

R00 will validate this backend behind Caddy TLS, together with the accepted frontend release and PostgreSQL 16.15, before S00 is allowed to touch a real server.

## Validation

The permanent Backend Quality Gate must pass at the exact closure head, including frozen dependency installation, vulnerability audit, Ruff, strict mypy, Django checks, migration drift, migrate-from-zero, PostgreSQL tests, OpenAPI, backup/restore rehearsal, production deployment checks, release manifest and bytecode compilation.

No real provider credentials are required or fabricated in R00.
