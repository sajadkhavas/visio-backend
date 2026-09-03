import logging

from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@require_http_methods(["GET", "HEAD"])
def health(request) -> JsonResponse:
    del request
    response = JsonResponse({"status": "ok", "service": "visio-backend"})
    response["Cache-Control"] = "no-store"
    return response


@require_http_methods(["GET", "HEAD"])
def readiness(request) -> JsonResponse:
    del request
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.warning("Readiness probe failed because PostgreSQL is unavailable.")
        response = JsonResponse(
            {"status": "unavailable", "service": "visio-backend"}, status=503
        )
        response["Cache-Control"] = "no-store"
        return response

    response = JsonResponse({"status": "ready", "service": "visio-backend"})
    response["Cache-Control"] = "no-store"
    return response
