from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower


class User(AbstractUser):
    """VISIO user model reserved before the first accepted application migration."""

    email = models.EmailField(unique=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="accounts_user_email_ci_unique",
            ),
        ]


class Address(models.Model):
    """Customer-owned address-book entry; shipping eligibility belongs to B05."""

    phone_validator = RegexValidator(
        regex=r"^\+?[0-9]{7,15}$",
        message="Use 7 to 15 digits with an optional leading +.",
    )
    country_code_validator = RegexValidator(
        regex=r"^[A-Z]{2}$",
        message="Use a two-letter uppercase country code.",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    label = models.CharField(max_length=64)
    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=16, validators=[phone_validator])
    country_code = models.CharField(
        max_length=2,
        default="IR",
        validators=[country_code_validator],
    )
    province = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=32)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-updated_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="accounts_one_default_address_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.label}: {self.city}"
