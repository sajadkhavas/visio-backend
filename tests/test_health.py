import pytest
from django.db import DatabaseError, connection
from django.test import Client

pytestmark = pytest.mark.django_db


def test_health_is_live_without_database_query(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("health endpoint must not touch the database")

    monkeypatch.setattr(connection, "cursor", fail_if_called)
    response = Client().get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "visio-backend"}
    assert response["Cache-Control"] == "no-store"


def test_readiness_checks_postgresql() -> None:
    response = Client().get("/ready/")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "visio-backend"}


def test_readiness_fails_closed_when_postgresql_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DatabaseError("database unavailable")

    monkeypatch.setattr(connection, "cursor", unavailable)
    response = Client().get("/ready/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "service": "visio-backend"}
