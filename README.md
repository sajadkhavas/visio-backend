# VISIO Backend

Canonical Python backend for VISIO.

B00 establishes the production-shaped Django foundation. Catalog, Cart, Checkout, Orders, Payment, Shipping and other commerce domains are intentionally out of scope until their registered phases.

## Runtime

- Python 3.13.15
- Django 5.2.17 LTS
- Django REST Framework 3.18.0
- PostgreSQL 16.15
- uv 0.12.9

## Local bootstrap

1. Install Python 3.13.15 and uv 0.12.9.
2. Copy `.env.example` to `.env` for your local shell/tooling; `.env` is ignored by Git.
3. Start PostgreSQL with `docker compose up -d postgres` or provide an equivalent PostgreSQL 16 instance.
4. Export the variables from `.env` in your shell. Django intentionally does not auto-load secret files.
5. Run `uv sync --frozen --all-groups`.
6. Run `uv run python manage.py migrate`.
7. Run `uv run python manage.py runserver`.

Foundation endpoints:

- `GET /health/` — liveness, does not query PostgreSQL
- `GET /ready/` — readiness, queries PostgreSQL and fails with 503 when unavailable
- `GET /api/v1/system/status/` — versioned API foundation
- `GET /api/v1/schema/` — OpenAPI schema

## Quality gate

The exact-head CI gate uses PostgreSQL 16 and proves frozen install, format/lint, mypy, Django checks, tests, migration drift, migrate-from-zero, OpenAPI generation, production deployment checks, immutable action pins and secret sanity.

See `docs/architecture/B00.md` and `docs/learning/B00_PYTHON_NOTES.md`.
