from typing import cast
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.test import Client

from apps.accounts.models import Address, User

pytestmark = pytest.mark.django_db

CSRF_PATH = "/api/v1/auth/csrf/"
ADDRESSES_PATH = "/api/v1/account/addresses/"


def create_user(email: str) -> User:
    return User.objects.create_user(
        username=uuid4().hex,
        email=email.lower(),
        password="Strong-Address-Pass!42",
    )


def csrf_token(client: Client) -> str:
    response = client.get(CSRF_PATH)
    assert response.status_code == 200
    return cast(str, response.json()["csrf_token"])


def address_payload(*, label: str, is_default: bool, country_code: str = "IR") -> dict[str, object]:
    return {
        "label": label,
        "recipient_name": "Customer Name",
        "recipient_phone": "+989121234567",
        "country_code": country_code,
        "province": "Alborz",
        "city": "Karaj",
        "postal_code": "1234567890",
        "address_line1": "Example street 1",
        "address_line2": "",
        "is_default": is_default,
    }


def authenticated_client(user: User) -> tuple[Client, str]:
    client = Client(enforce_csrf_checks=True)
    client.force_login(user, backend="apps.accounts.backends.EmailAuthenticationBackend")
    return client, csrf_token(client)


def test_setting_new_default_address_atomically_clears_previous_default() -> None:
    user = create_user("address@example.com")
    client, token = authenticated_client(user)

    first = client.post(
        ADDRESSES_PATH,
        address_payload(label="Home", is_default=True),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    second = client.post(
        ADDRESSES_PATH,
        address_payload(label="Work", is_default=True, country_code="ir"),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["country_code"] == "IR"

    first_address = Address.objects.get(pk=first.json()["id"])
    second_address = Address.objects.get(pk=second.json()["id"])
    assert first_address.is_default is False
    assert second_address.is_default is True
    assert Address.objects.filter(user=user, is_default=True).count() == 1


def test_address_queryset_never_exposes_another_users_record() -> None:
    owner = create_user("owner@example.com")
    stranger = create_user("stranger@example.com")
    address = Address.objects.create(
        user=owner,
        label="Private",
        recipient_name="Owner",
        recipient_phone="+989121234567",
        country_code="IR",
        province="Tehran",
        city="Tehran",
        postal_code="1111111111",
        address_line1="Private address",
        is_default=True,
    )

    client, _token = authenticated_client(stranger)
    detail = client.get(f"{ADDRESSES_PATH}{address.pk}/")
    listing = client.get(ADDRESSES_PATH)

    assert detail.status_code == 404
    assert listing.status_code == 200
    assert listing.json() == []


def test_deleting_default_address_does_not_guess_a_replacement() -> None:
    user = create_user("delete-default@example.com")
    first = Address.objects.create(
        user=user,
        label="Secondary",
        recipient_name="Customer",
        recipient_phone="+989121234567",
        country_code="IR",
        province="Alborz",
        city="Karaj",
        postal_code="1234567890",
        address_line1="Secondary",
        is_default=False,
    )
    default = Address.objects.create(
        user=user,
        label="Default",
        recipient_name="Customer",
        recipient_phone="+989121234567",
        country_code="IR",
        province="Alborz",
        city="Karaj",
        postal_code="1234567891",
        address_line1="Default",
        is_default=True,
    )
    client, token = authenticated_client(user)

    response = client.delete(
        f"{ADDRESSES_PATH}{default.pk}/",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == 204
    first.refresh_from_db()
    assert first.is_default is False
    assert not Address.objects.filter(user=user, is_default=True).exists()


def test_address_validation_rejects_invalid_phone() -> None:
    user = create_user("invalid-address@example.com")
    client, token = authenticated_client(user)
    payload = address_payload(label="Bad", is_default=False)
    payload["recipient_phone"] = "not-a-phone"

    response = client.post(
        ADDRESSES_PATH,
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )

    assert response.status_code == 400
    assert "recipient_phone" in response.json()["errors"]


def test_postgresql_constraint_rejects_two_default_addresses_for_same_user() -> None:
    user = create_user("constraint@example.com")
    Address.objects.create(
        user=user,
        label="One",
        recipient_name="Customer",
        recipient_phone="+989121234567",
        country_code="IR",
        province="Alborz",
        city="Karaj",
        postal_code="1234567890",
        address_line1="One",
        is_default=True,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Address.objects.create(
                user=user,
                label="Two",
                recipient_name="Customer",
                recipient_phone="+989121234568",
                country_code="IR",
                province="Alborz",
                city="Karaj",
                postal_code="1234567891",
                address_line1="Two",
                is_default=True,
            )


def test_database_rejects_case_insensitive_duplicate_emails() -> None:
    create_user("case@example.com")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create_user(
                username=uuid4().hex,
                email="CASE@EXAMPLE.COM",
                password="Another-Strong-Pass!42",
            )
