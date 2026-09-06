from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from django.http import HttpRequest, HttpResponse

_REQUEST_ID = ContextVar[str]("visio_request_id", default="-")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_REQUEST_LOGGER = logging.getLogger("visio.request")


def current_request_id() -> str:
    return _REQUEST_ID.get()


def normalize_request_id(value: str) -> str:
    candidate = value.strip()
    if _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


class JsonLogFormatter(logging.Formatter):
    """Emit bounded structured logs without request bodies, query strings, or credentials."""

    _EXTRA_FIELDS = (
        "event",
        "request_id",
        "http_method",
        "path",
        "status_code",
        "duration_ms",
    )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if request_id != "-":
            payload["request_id"] = request_id

        for field in self._EXTRA_FIELDS:
            if field == "request_id":
                continue
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class RequestObservabilityMiddleware:
    """Attach a safe request id and emit one structured completion/failure event per request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = normalize_request_id(request.headers.get("X-Request-ID", ""))
        token = _REQUEST_ID.set(request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
        except Exception:
            duration_ms = round((time.monotonic() - started) * 1000, 3)
            _REQUEST_LOGGER.exception(
                "request.failed",
                extra={
                    "event": "request.failed",
                    "request_id": request_id,
                    "http_method": request.method,
                    "path": request.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            raise
        else:
            duration_ms = round((time.monotonic() - started) * 1000, 3)
            response["X-Request-ID"] = request_id
            _REQUEST_LOGGER.info(
                "request.complete",
                extra={
                    "event": "request.complete",
                    "request_id": request_id,
                    "http_method": request.method,
                    "path": request.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
            return response
        finally:
            _REQUEST_ID.reset(token)
