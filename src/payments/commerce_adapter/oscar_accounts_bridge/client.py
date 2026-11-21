"""Django Oscar bridge: only provider-token references cross service boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    reference: str
    amount: Decimal
    currency: str
    customer_id: str
    payment_method_id: str
    metadata: dict[str, Any] | None = None
    redirect_url: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "amount": str(self.amount),
            "currency": self.currency.upper(),
            "customer_id": self.customer_id,
            "payment_method_id": self.payment_method_id,
            "metadata": self.metadata or {},
            "redirect_url": self.redirect_url or "",
        }


class PaymentMicroserviceClient:
    def __init__(
        self, *, rest_base_url: str = "http://localhost:8000/api",
        rest_token: str, timeout: float = 15.0,
    ) -> None:
        self.rest_base_url = rest_base_url.rstrip("/")
        self.rest_token = rest_token
        self.timeout = timeout

    def request_payment(self, request: PaymentRequest) -> dict[str, Any]:
        response = httpx.post(
            f"{self.rest_base_url}/payment-intents/charge/",
            json=request.to_payload(),
            headers={"Authorization": f"Token {self.rest_token}"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
