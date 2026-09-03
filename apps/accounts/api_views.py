from typing import cast

from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db.models import QuerySet
from django.http import HttpRequest
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import Address, User
from .serializers import (
    AccountSerializer,
    AddressSerializer,
    CsrfTokenSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    RegistrationSerializer,
    normalize_email,
)


def _django_request(request: Request) -> HttpRequest:
    return cast(HttpRequest, request._request)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfTokenView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    throttle_classes: list[type] = []

    @extend_schema(responses={200: CsrfTokenSerializer})
    def get(self, request: Request) -> Response:
        return Response({"csrf_token": get_token(_django_request(request))})


@method_decorator(csrf_protect, name="dispatch")
class RegistrationView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    @extend_schema(request=RegistrationSerializer, responses={201: AccountSerializer})
    def post(self, request: Request) -> Response:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        django_login(
            _django_request(request),
            user,
            backend="apps.accounts.backends.EmailAuthenticationBackend",
        )
        return Response(AccountSerializer(user).data, status=status.HTTP_201_CREATED)


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    @extend_schema(request=LoginSerializer, responses={200: AccountSerializer})
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=_django_request(request),
            email=normalize_email(str(serializer.validated_data["email"])),
            password=str(serializer.validated_data["password"]),
        )
        if not isinstance(user, User):
            raise ValidationError({"non_field_errors": ["Invalid email or password."]})

        django_login(
            _django_request(request),
            user,
            backend="apps.accounts.backends.EmailAuthenticationBackend",
        )
        return Response(AccountSerializer(user).data)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [AllowAny]
    throttle_classes: list[type] = []

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        django_logout(_django_request(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class CurrentAccountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: AccountSerializer})
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        return Response(AccountSerializer(user).data)

    @extend_schema(request=AccountSerializer, responses={200: AccountSerializer})
    def patch(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = AccountSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={200: AccountSerializer})
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        serializer = PasswordChangeSerializer(data=request.data, context={"user": user})
        serializer.is_valid(raise_exception=True)
        updated_user = serializer.apply()
        update_session_auth_hash(_django_request(request), updated_user)
        return Response(AccountSerializer(updated_user).data)


class AddressListCreateView(generics.ListCreateAPIView):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Address]:
        user = cast(User, self.request.user)
        return Address.objects.filter(user=user)


class AddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Address]:
        user = cast(User, self.request.user)
        return Address.objects.filter(user=user)
