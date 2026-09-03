from django.contrib.auth import get_user_model
from django.test import Client


def test_custom_user_model_is_installed_before_domain_work() -> None:
    user_model = get_user_model()

    assert user_model._meta.label == "accounts.User"


def test_versioned_api_foundation_is_live() -> None:
    response = Client().get("/api/v1/system/status/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "visio-backend",
        "status": "ok",
        "api_version": "v1",
    }


def test_openapi_schema_endpoint_is_available() -> None:
    response = Client().get("/api/v1/schema/")

    assert response.status_code == 200
    assert b"openapi" in response.content.lower()
