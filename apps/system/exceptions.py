from http import HTTPStatus
from typing import Any

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def problem_details_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    status_code = response.status_code
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = "Request failed"

    problem: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": "The request could not be completed.",
    }

    request = context.get("request")
    if request is not None:
        problem["instance"] = request.path

    if isinstance(exc, ValidationError):
        problem["detail"] = "Request validation failed."
        problem["errors"] = response.data
    elif isinstance(response.data, dict) and "detail" in response.data:
        problem["detail"] = str(response.data["detail"])

    return Response(
        problem,
        status=status_code,
        headers=response.headers,
        content_type="application/problem+json",
    )
