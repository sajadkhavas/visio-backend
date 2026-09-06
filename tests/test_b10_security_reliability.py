from __future__ import annotations

import json
import logging
import re
from io import StringIO

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, override_settings

from apps.system.observability import JsonLogFormatter

pytestmark = pytest.mark.django_db

LOGIN_PATH = "/api/v1/auth/login/"
CSRF_PATH = "/api/v1/auth/csrf/"


def test_health_preserves_safe_request_id() -> None:
    response = Client().get("/health/", HTTP_X_REQUEST_ID="edge-request-42")

    assert response.status_code == 200
    assert response["X-Request-ID"] == "edge-request-42"


def test_invalid_request_id_is_replaced_with_bounded_server_id() -> None:
    response = Client().get("/health/", HTTP_X_REQUEST_ID="bad request id with spaces")

    assert response.status_code == 200
    request_id = response["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)


def test_json_log_formatter_emits_bounded_structured_fields() -> None:
    record = logging.LogRecord(
        name="visio.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request.complete",
        args=(),
        exc_info=None,
    )
    record.event = "request.complete"
    record.request_id = "req-123"
    record.http_method = "GET"
    record.path = "/api/v1/catalog/products/"
    record.status_code = 200
    record.duration_ms = 12.5

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["event"] == "request.complete"
    assert payload["request_id"] == "req-123"
    assert payload["http_method"] == "GET"
    assert payload["path"] == "/api/v1/catalog/products/"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5
    assert "query_string" not in payload
    assert "request_body" not in payload


def test_login_rejects_missing_csrf_token() -> None:
    client = Client(enforce_csrf_checks=True)

    response = client.post(
        LOGIN_PATH,
        data={"email": "attacker@example.invalid", "password": "invalid-password"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response["Content-Type"].startswith("application/problem+json")


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
        "EXCEPTION_HANDLER": "apps.system.exceptions.problem_details_exception_handler",
        "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework.authentication.SessionAuthentication",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "auth_register": "5/min",
            "auth_login": "2/min",
        },
    }
)
def test_login_rate_limit_fails_closed_after_scope_budget() -> None:
    cache.clear()
    client = Client(enforce_csrf_checks=True)
    csrf_response = client.get(CSRF_PATH)
    assert csrf_response.status_code == 200
    csrf_token = csrf_response.json()["csrf_token"]

    statuses = []
    for _ in range(3):
        response = client.post(
            LOGIN_PATH,
            data={"email": "rate-limit@example.invalid", "password": "invalid-password"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        statuses.append(response.status_code)

    assert statuses == [400, 400, 429]
    cache.clear()


def test_business_integrity_command_passes_on_consistent_database() -> None:
    output = StringIO()

    call_command("verify_business_integrity", stdout=output)

    assert "Business integrity verification passed" in output.getvalue()
