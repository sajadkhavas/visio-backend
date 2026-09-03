from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from apps.system.exceptions import problem_details_exception_handler


def test_validation_errors_use_problem_details_semantics() -> None:
    request = APIRequestFactory().post("/api/v1/example/", {}, format="json")
    response = problem_details_exception_handler(
        ValidationError({"field": ["This field is required."]}),
        {"request": request},
    )

    assert response is not None
    assert response.status_code == 400
    assert response.data["type"] == "about:blank"
    assert response.data["title"] == "Bad Request"
    assert response.data["status"] == 400
    assert response.data["detail"] == "Request validation failed."
    assert response.data["instance"] == "/api/v1/example/"
    assert "errors" in response.data
