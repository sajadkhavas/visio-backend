# B00 Python Learning Notes

## Virtual environments and dependencies

`uv` reads `pyproject.toml`, resolves exact transitive dependencies into `uv.lock`, and installs them into an isolated environment. The accepted build uses `uv sync --frozen --all-groups`, so CI cannot silently change dependency versions.

## Packages, modules and imports

`config` and every directory under `apps` containing `__init__.py` is a Python package. Files such as `views.py` and `models.py` are modules. Imports connect those modules without copying code.

## Classes and inheritance

`accounts.User` inherits `AbstractUser`. This reuses Django's tested user behavior while making the project's user model swappable from the first migration. `ApiStatusView` inherits DRF's `APIView`.

## Type hints

Annotations such as `-> JsonResponse` and `list[str]` describe expected values. mypy checks these contracts statically; runtime behavior is still enforced by tests.

## Exceptions

Production configuration raises `ImproperlyConfigured` when required environment values are absent. The readiness endpoint catches database exceptions and returns 503 without leaking the underlying database error.

## Settings and environment variables

Settings are Python modules. Local, test and production modules import the common baseline and then apply environment-specific policy. Real secrets never belong in source control.

## Django project vs app

`config` is project-level wiring. `apps/accounts` and `apps/system` are apps with focused responsibilities. Later business domains get their own apps instead of growing one giant module.

## ORM and migrations

A Django model is a Python class representing persisted data. A migration is a versioned database schema operation derived from model state. B00 generates the first `accounts.User` migration and proves the entire schema can migrate from an empty PostgreSQL database.

## HTTP and API concepts

A URL maps an HTTP request to a view. Status codes communicate outcomes. `/health/` answers whether the process is alive; `/ready/` answers whether it can currently reach its required database dependency.

## Automated testing

pytest executes repeatable assertions. B00 tests behavior at HTTP boundaries and uses the same PostgreSQL major selected for production, reducing the gap between local assumptions and deployment reality.
