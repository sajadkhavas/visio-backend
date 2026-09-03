from typing import cast
from uuid import uuid4

import pytest
from apps.accounts.models import User
from django.core.cache import cache
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db

CSRF_PATH = "/api/v1/auth/csrf/"
REGISTER_PATH = "/api/v1/auth/register/"
LOGIN_PATH = "/api/v1/auth/login/"
LOGOUT_PATH = "/api/v1/auth/logout/"
ME_PATH = "/api/v1/account/me/"
PASSWORD_PATH = "/api/v1/account/password/"


def csrf_token(client: Client) -> str:
    response = client.get(CSRF_PATH)
    assert response.status_code == 200
    return cast(str, response.json()["csrf_token"])


def create_user(email: str, password: str = "Strong-Test-Pass!42") -> User:
    return User.objects.create_user(
        username=uuid4().hex,
        email=email.lower(),
        password=password,
        first_name="Test",
        last_name="User",
    )


def test_registration_requires_csrf_normalizes_email_and_creates_session() -> None:
    payload = {
        "email": "Customer@Example.COM",
        "password": "Solid-Registration-Pass!42",
        "first_name": "Customer",
        "last_name": "One",
    }

    blocked_client = Client(enforce_csrf_checks=True)
    blocked = blocked_client.post(REGISTER_PATH, payload, content_type="application/json")
    assert blocked.status_code == 403
    assert blocked.headers["Content-Type"].startswith("application/problem+json")
    assert blocked.json()["detail"] == "CSRF verification failed."

    client = Client(enforce_csrf_checks=True)
    token = csrf_token(client)
    created = client.post(
        REGISTER_PATH,
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert created.status_code == 201
    assert created.json()["email"] == "customer@example.com"
    assert "username" not in created.json()

    user = User.objects.get(email="customer@example.com")
    assert user.username != user.email
    assert len(user.username) == 32

    current = client.get(ME_PATH)
    assert current.status_code == 200
    assert current.json()["email"] == "customer@example.com"


def test_registration_rejects_case_insensitive_duplicate_email() -> None:
    first = Client(enforce_csrf_checks=True)
    first_token = csrf_token(first)
    response = first.post(
        REGISTER_PATH,
        {"email": "duplicate@example.com", "password": "Solid-Duplicate-Pass!42"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=first_token,
    )
    assert response.status_code == 201

    second = Client(enforce_csrf_checks=True)
    second_token = csrf_token(second)
    duplicate = second.post(
        REGISTER_PATH,
        {"email": "DUPLICATE@EXAMPLE.COM", "password": "Another-Solid-Pass!42"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=second_token,
    )

    assert duplicate.status_code == 400
    assert "email" in duplicate.json()["errors"]


def test_login_errors_are_generic_and_success_creates_session() -> None:
    create_user("login@example.com")
    client = Client(enforce_csrf_checks=True)
    token = csrf_token(client)

    unknown = client.post(
        LOGIN_PATH,
        {"email": "unknown@example.com", "password": "Wrong-Pass!42"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    wrong_password = client.post(
        LOGIN_PATH,
        {"email": "login@example.com", "password": "Wrong-Pass!42"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert unknown.status_code == 400
    assert wrong_password.status_code == 400
    assert unknown.json()["errors"] == wrong_password.json()["errors"]

    success = client.post(
        LOGIN_PATH,
        {"email": "LOGIN@EXAMPLE.COM", "password": "Strong-Test-Pass!42"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert success.status_code == 200
    assert client.get(ME_PATH).status_code == 200


def test_profile_email_is_not_silently_changed_and_password_rotation_keeps_session() -> None:
    user = create_user("profile@example.com")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user, backend="apps.accounts.backends.EmailAuthenticationBackend")
    token = csrf_token(client)

    profile = client.patch(
        ME_PATH,
        {"first_name": "Updated", "last_name": "Customer"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert profile.status_code == 200
    assert profile.json()["first_name"] == "Updated"

    email_change = client.patch(
        ME_PATH,
        {"email": "new@example.com"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert email_change.status_code == 400
    assert "email" in email_change.json()["errors"]

    wrong_current = client.post(
        PASSWORD_PATH,
        {"current_password": "wrong", "new_password": "New-Solid-Pass!42"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert wrong_current.status_code == 400

    changed = client.post(
        PASSWORD_PATH,
        {"current_password": "Strong-Test-Pass!42", "new_password": "New-Solid-Pass!42"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert changed.status_code == 200
    assert client.get(ME_PATH).status_code == 200

    user.refresh_from_db()
    assert user.check_password("New-Solid-Pass!42")
    assert not user.check_password("Strong-Test-Pass!42")


def test_logout_requires_csrf_and_clears_session() -> None:
    user = create_user("logout@example.com")
    client = Client(enforce_csrf_checks=True)
    client.force_login(user, backend="apps.accounts.backends.EmailAuthenticationBackend")

    blocked = client.post(LOGOUT_PATH)
    assert blocked.status_code == 403

    token = csrf_token(client)
    logged_out = client.post(LOGOUT_PATH, HTTP_X_CSRFTOKEN=token)
    assert logged_out.status_code == 204
    denied = client.get(ME_PATH)
    assert denied.status_code == 403
    assert denied.headers["Content-Type"].startswith("application/problem+json")


def test_login_scope_throttles_repeated_requests() -> None:
    cache.clear()
    throttled_rest_framework = {
        "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
        "EXCEPTION_HANDLER": "apps.system.exceptions.problem_details_exception_handler",
        "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework.authentication.SessionAuthentication",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "auth_register": "5/min",
            "auth_login": "1/min",
        },
    }

    with override_settings(REST_FRAMEWORK=throttled_rest_framework):
        client = Client(enforce_csrf_checks=True)
        token = csrf_token(client)
        first = client.post(
            LOGIN_PATH,
            {"email": "nobody@example.com", "password": "Wrong-Pass!42"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        second = client.post(
            LOGIN_PATH,
            {"email": "nobody@example.com", "password": "Wrong-Pass!42"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )

    cache.clear()
    assert first.status_code == 400
    assert second.status_code == 429
    assert second.json()["status"] == 429


def test_openapi_contains_b01_public_routes() -> None:
    response = Client().get("/api/v1/schema/")
    assert response.status_code == 200
    schema = response.content.decode()
    assert "/api/v1/auth/login/" in schema
    assert "/api/v1/account/addresses/" in schema
