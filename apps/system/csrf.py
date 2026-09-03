from django.http import HttpRequest, JsonResponse


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    del reason
    return JsonResponse(
        {
            "type": "about:blank",
            "title": "Forbidden",
            "status": 403,
            "detail": "CSRF verification failed.",
            "instance": request.path,
        },
        status=403,
        content_type="application/problem+json",
    )
