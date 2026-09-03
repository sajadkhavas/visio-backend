from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest

from .models import User


class EmailAuthenticationBackend(ModelBackend):
    """Authenticate public customers by email while keeping username internal."""

    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        del request
        identifier = kwargs.get("email") or username
        if not identifier or password is None:
            return None

        email = str(identifier).strip().lower()
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Match Django's default backend behavior: perform a dummy password hash
            # so an unknown account is not an obvious fast-path timing oracle.
            dummy = User(username="timing-dummy", email="timing-dummy@example.invalid")
            dummy.set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
