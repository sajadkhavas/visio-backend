from __future__ import annotations

import json
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderRejectedError,
    ProviderRequestResult,
    ProviderVerifyResult,
)


class ZarinPalProvider:
    name = "zarinpal"

    def __init__(
        self,
        *,
        merchant_id: str,
        sandbox: bool = False,
        timeout_seconds: float = 10.0,
        access_token: str = "",
    ) -> None:
        merchant_id = merchant_id.strip()
        if not merchant_id:
            raise ProviderConfigurationError("ZarinPal merchant ID is required.")
        if timeout_seconds <= 0:
            raise ProviderConfigurationError("Payment provider timeout must be positive.")
        self.merchant_id = merchant_id
        self.sandbox = sandbox
        self.timeout_seconds = timeout_seconds
        self.access_token = access_token.strip()
        self.base_url = (
            "https://sandbox.zarinpal.com" if sandbox else "https://payment.zarinpal.com"
        )
        self.graphql_url = "https://next.zarinpal.com/api/v4/graphql/"

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        authorization: str = "",
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "VISIO-Payment/1.0",
        }
        if authorization:
            headers["Authorization"] = f"Bearer {authorization}"
        request = Request(
            url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise ProviderError(f"ZarinPal returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise ProviderError("ZarinPal could not be reached.") from exc
        except TimeoutError as exc:
            raise ProviderError("ZarinPal request timed out.") from exc

        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("ZarinPal returned invalid JSON.") from exc
        if not isinstance(decoded, dict):
            raise ProviderError("ZarinPal returned an invalid response shape.")
        return cast(dict[str, Any], decoded)

    @staticmethod
    def _data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if isinstance(data, dict):
            return cast(dict[str, Any], data)
        errors = payload.get("errors")
        raise ProviderRejectedError(f"ZarinPal rejected the request: {errors!r}")

    @staticmethod
    def _code(data: dict[str, Any]) -> int:
        value = data.get("code")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProviderError("ZarinPal response did not contain a numeric code.")
        return value

    @staticmethod
    def _text(data: dict[str, Any], key: str) -> str:
        value = data.get(key, "")
        if value is None:
            return ""
        if isinstance(value, (str, int)):
            return str(value)
        return ""

    def request_payment(
        self,
        *,
        amount_rial: int,
        callback_url: str,
        description: str,
        mobile: str = "",
        email: str = "",
    ) -> ProviderRequestResult:
        if amount_rial < 1_000:
            raise ProviderRejectedError("ZarinPal payment amount must be at least 1,000 IRR.")
        payload: dict[str, Any] = {
            "merchant_id": self.merchant_id,
            "amount": amount_rial,
            "callback_url": callback_url,
            "description": description,
        }
        metadata: dict[str, str] = {}
        if mobile:
            metadata["mobile"] = mobile
        if email:
            metadata["email"] = email
        if metadata:
            payload["metadata"] = metadata

        response = self._post_json(f"{self.base_url}/pg/v4/payment/request.json", payload)
        data = self._data(response)
        code = self._code(data)
        authority = self._text(data, "authority")
        message = self._text(data, "message")
        if code != 100 or not authority:
            raise ProviderRejectedError(f"ZarinPal request failed with code {code}: {message}")
        return ProviderRequestResult(
            code=code,
            message=message,
            authority=authority,
            redirect_url=f"{self.base_url}/pg/StartPay/{authority}",
        )

    def verify_payment(self, *, amount_rial: int, authority: str) -> ProviderVerifyResult:
        response = self._post_json(
            f"{self.base_url}/pg/v4/payment/verify.json",
            {
                "merchant_id": self.merchant_id,
                "amount": amount_rial,
                "authority": authority,
            },
        )
        data = self._data(response)
        code = self._code(data)
        message = self._text(data, "message")
        if code not in {100, 101}:
            raise ProviderRejectedError(f"ZarinPal verification failed with code {code}: {message}")
        ref_id = self._text(data, "ref_id")
        if not ref_id:
            raise ProviderError("Verified ZarinPal response did not include ref_id.")
        return ProviderVerifyResult(
            code=code,
            message=message,
            ref_id=ref_id,
            masked_card=self._text(data, "card_pan"),
            card_hash=self._text(data, "card_hash"),
        )

    def reverse_payment(self, *, authority: str) -> ProviderVerifyResult:
        response = self._post_json(
            f"{self.base_url}/pg/v4/payment/reverse.json",
            {"merchant_id": self.merchant_id, "authority": authority},
        )
        data = self._data(response)
        code = self._code(data)
        message = self._text(data, "message")
        if code != 100:
            raise ProviderRejectedError(f"ZarinPal reversal failed with code {code}: {message}")
        return ProviderVerifyResult(
            code=code,
            message=message,
            ref_id=self._text(data, "ref_id"),
        )

    def refund_payment(
        self,
        *,
        session_id: str,
        amount_rial: int,
        description: str,
        reason: str,
    ) -> str:
        if not self.access_token:
            raise ProviderConfigurationError(
                "ZarinPal access token is required for the official refund GraphQL API."
            )
        query = """
        mutation AddRefund(
          $session_id: ID!, $amount: BigInteger!, $description: String,
          $reason: RefundReasonEnum
        ) {
          resource: AddRefund(
            session_id: $session_id, amount: $amount,
            description: $description, reason: $reason
          ) { id amount }
        }
        """
        response = self._post_json(
            self.graphql_url,
            {
                "query": query,
                "variables": {
                    "session_id": session_id,
                    "amount": amount_rial,
                    "description": description,
                    "reason": reason,
                },
            },
            authorization=self.access_token,
        )
        data = response.get("data")
        if not isinstance(data, dict):
            raise ProviderRejectedError(f"ZarinPal refund failed: {response.get('errors')!r}")
        resource = data.get("resource")
        if not isinstance(resource, dict):
            raise ProviderRejectedError("ZarinPal refund response did not include a resource.")
        refund_id = resource.get("id")
        if not isinstance(refund_id, (str, int)):
            raise ProviderError("ZarinPal refund response did not include an id.")
        return str(refund_id)
