import re
from typing import Any, cast
from uuid import uuid4

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from .models import Address, User


def normalize_email(value: str) -> str:
    return value.strip().lower()


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "date_joined"]
        read_only_fields = ["id", "email", "date_joined"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        initial_data = getattr(self, "initial_data", {})
        if isinstance(initial_data, dict) and "email" in initial_data:
            raise serializers.ValidationError(
                {"email": "Email changes require a dedicated verification workflow."}
            )
        return attrs


class RegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        email = normalize_email(str(attrs["email"]))
        attrs["email"] = email

        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "An account with this email already exists."})

        candidate = User(
            username="password-validation",
            email=email,
            first_name=str(attrs.get("first_name", "")),
            last_name=str(attrs.get("last_name", "")),
        )
        try:
            password_validation.validate_password(str(attrs["password"]), candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data: dict[str, Any]) -> User:
        try:
            with transaction.atomic():
                return User.objects.create_user(
                    username=uuid4().hex,
                    email=normalize_email(str(validated_data["email"])),
                    password=str(validated_data["password"]),
                    first_name=str(validated_data.get("first_name", "")),
                    last_name=str(validated_data.get("last_name", "")),
                )
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"email": "An account with this email already exists."}
            ) from exc


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = cast(User, self.context["user"])
        if not user.check_password(str(attrs["current_password"])):
            raise serializers.ValidationError(
                {"current_password": "The current password is incorrect."}
            )

        try:
            password_validation.validate_password(str(attrs["new_password"]), user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc
        return attrs

    def apply(self) -> User:
        user = cast(User, self.context["user"])
        user.set_password(str(self.validated_data["new_password"]))
        user.save(update_fields=["password"])
        return user


class CsrfTokenSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class AddressSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    country_code = serializers.CharField(max_length=2)
    recipient_phone = serializers.CharField(max_length=16)

    class Meta:
        model = Address
        fields = [
            "id",
            "user",
            "label",
            "recipient_name",
            "recipient_phone",
            "country_code",
            "province",
            "city",
            "postal_code",
            "address_line1",
            "address_line2",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_country_code(self, value: str) -> str:
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", normalized):
            raise serializers.ValidationError("Use a two-letter country code.")
        return normalized

    def validate_recipient_phone(self, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"\+?[0-9]{7,15}", normalized):
            raise serializers.ValidationError("Use 7 to 15 digits with an optional leading +.")
        return normalized

    def create(self, validated_data: dict[str, Any]) -> Address:
        user = cast(User, validated_data["user"])
        make_default = bool(validated_data.get("is_default", False))

        try:
            with transaction.atomic():
                User.objects.select_for_update().only("pk").get(pk=user.pk)
                if make_default:
                    Address.objects.filter(user=user, is_default=True).update(is_default=False)
                return Address.objects.create(**validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"is_default": "A default-address conflict occurred. Retry the request."}
            ) from exc

    def update(self, instance: Address, validated_data: dict[str, Any]) -> Address:
        validated_data.pop("user", None)
        make_default = bool(validated_data.get("is_default", False))

        try:
            with transaction.atomic():
                User.objects.select_for_update().only("pk").get(pk=instance.user_id)
                if make_default:
                    Address.objects.filter(
                        user_id=instance.user_id,
                        is_default=True,
                    ).exclude(pk=instance.pk).update(is_default=False)

                for field, value in validated_data.items():
                    setattr(instance, field, value)
                instance.save()
                return instance
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"is_default": "A default-address conflict occurred. Retry the request."}
            ) from exc
