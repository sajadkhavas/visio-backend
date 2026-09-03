from django.urls import path

from .api_views import (
    AddressDetailView,
    AddressListCreateView,
    CsrfTokenView,
    CurrentAccountView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    RegistrationView,
)

urlpatterns = [
    path("auth/csrf/", CsrfTokenView.as_view(), name="auth-csrf"),
    path("auth/register/", RegistrationView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("account/me/", CurrentAccountView.as_view(), name="account-me"),
    path("account/password/", PasswordChangeView.as_view(), name="account-password"),
    path("account/addresses/", AddressListCreateView.as_view(), name="address-list"),
    path("account/addresses/<int:pk>/", AddressDetailView.as_view(), name="address-detail"),
]
