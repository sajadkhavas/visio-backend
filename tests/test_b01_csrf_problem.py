import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def test_csrf_failure_is_rfc9457_style_problem_details() -> None:
    client = Client(enforce_csrf_checks=True)
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "nobody@example.com", "password": "Wrong-Pass!42"},
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.headers["Content-Type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Forbidden",
        "status": 403,
        "detail": "CSRF verification failed.",
        "instance": "/api/v1/auth/login/",
    }
