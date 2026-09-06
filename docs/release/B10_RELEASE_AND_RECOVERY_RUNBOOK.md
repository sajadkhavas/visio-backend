# VISIO B10 — Backend Release & Recovery Runbook

## Purpose

This runbook defines the accepted backend-level release/recovery contract. It does not authorize production deployment by itself. R00 owns production-shaped rehearsal and S00 owns the real server deployment.

## Release identity

For an exact checked-out commit:

```bash
uv run python scripts/build_release_manifest.py --output /tmp/visio-release.json
sha256sum /tmp/visio-release.json
```

The manifest records the exact Git SHA, Python patch version, `uv.lock` hash and tracked-file hashes. Build it from the exact accepted release SHA; do not modify source files after generation.

## Pre-release verification

Run on PostgreSQL with the frozen dependency set:

```bash
uv lock --check
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy apps config tests
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate --noinput
uv run python manage.py verify_business_integrity
uv run pytest
uv run python manage.py spectacular --file /tmp/visio-openapi.yaml --validate
uv run python scripts/check_deployment.py
```

The permanent GitHub quality gate additionally performs dependency vulnerability auditing, action-pin/secret checks, recovery rehearsal and manifest reproducibility.

## Backup contract

Required environment variables:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- optional `POSTGRES_PORT` (default 5432)
- `VISIO_BACKUP_PATH`

Example:

```bash
export VISIO_BACKUP_PATH=/secure/backups/visio-$(date -u +%Y%m%dT%H%M%SZ).dump
bash scripts/backup_postgres.sh
```

Expected outputs:

- custom-format PostgreSQL dump at `$VISIO_BACKUP_PATH`;
- SHA-256 checksum at `${VISIO_BACKUP_PATH}.sha256`;
- restrictive file permissions.

The script refuses to overwrite an existing archive/checksum pair.

## Disposable restore rehearsal

Never point `VISIO_RESTORE_DATABASE` at the source production database. Create a disposable target first, then restore:

```bash
export VISIO_RESTORE_DATABASE=visio_restore_check
createdb \
  --host="$POSTGRES_HOST" \
  --port="${POSTGRES_PORT:-5432}" \
  --username="$POSTGRES_USER" \
  "$VISIO_RESTORE_DATABASE"

bash scripts/restore_postgres.sh

POSTGRES_DB="$VISIO_RESTORE_DATABASE" uv run python manage.py migrate --check
POSTGRES_DB="$VISIO_RESTORE_DATABASE" uv run python manage.py verify_business_integrity
```

After evidence is captured, remove the disposable database:

```bash
dropdb \
  --host="$POSTGRES_HOST" \
  --port="${POSTGRES_PORT:-5432}" \
  --username="$POSTGRES_USER" \
  "$VISIO_RESTORE_DATABASE"
```

The restore script verifies the archive checksum before `pg_restore` and refuses a restore target equal to `POSTGRES_DB`.

## Recovery decision rule

A backup is not accepted merely because `pg_dump` returned success. Accepted recovery evidence requires:

1. checksum verification;
2. successful restore into a disposable target;
3. no unapplied migrations in the restored target;
4. `verify_business_integrity` PASS;
5. explicit destruction of the disposable target after rehearsal.

## Production configuration boundary

Production settings require explicit strong configuration and reject wildcard hosts, insecure trusted CSRF origins, disabled HTTPS redirect and downgrade-capable PostgreSQL SSL modes. Credentials remain environment-only.

HSTS `includeSubDomains` and preload remain deferred until R00/S00 prove the whole domain/subdomain TLS contract. Do not switch either setting merely to silence a deployment warning.

## Observability boundary

Every request receives a bounded `X-Request-ID` and a structured JSON completion/failure event. Application request logging intentionally excludes request bodies and query strings. Infrastructure log collection/retention is an S00 operational concern.

## Rollback boundary

B10 creates reproducible release identity but does not claim a live process manager, proxy, or symlink topology. R00 must prove release activation and rollback against the production-shaped deployment mechanism selected for VISIO. Database rollback must not be improvised by reversing destructive migrations; backup/restore and forward recovery procedures require phase-specific evidence.

## Accepted B10 rehearsal evidence

Implementation Gate #388 / run `34034532159` successfully performed:

- PostgreSQL 16.15 dump creation;
- SHA-256 verification;
- disposable database creation;
- restore of the dump;
- restored migration-state verification;
- restored audit/order/payment/reconciliation integrity verification;
- disposable target cleanup.

This is backend-level recovery evidence. It is not a substitute for R00/S00 server-level rehearsal.
