from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    """Base class for payment-provider failures."""


class ProviderConfigurationError(ProviderError):
    pass


class ProviderRejectedError(ProviderError):
    pass


@dataclass(frozen=True)
class ProviderRequestResult:
    code: int
    message: str
    authority: str
    redirect_url: str


@dataclass(frozen=True)
class ProviderVerifyResult:
    code: int
    message: str
    ref_id: str
    masked_card: str = ""
    card_hash: str = ""


class PaymentProvider(Protocol):
    name: str

    def request_payment(
        self,
        *,
        amount_rial: int,
        callback_url: str,
        description: str,
        mobile: str = "",
        email: str = "",
    ) -> ProviderRequestResult: ...

    def verify_payment(self, *, amount_rial: int, authority: str) -> ProviderVerifyResult: ...

    def reverse_payment(self, *, authority: str) -> ProviderVerifyResult: ...

    def refund_payment(
        self,
        *,
        session_id: str,
        amount_rial: int,
        description: str,
        reason: str,
    ) -> str: ...
