"""Django Oscar checkout integration; card collection must happen at Flutterwave."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .client import PaymentMicroserviceClient, PaymentRequest


class FlutterwaveCheckoutBridge:
    def __init__(self, *, client: PaymentMicroserviceClient) -> None:
        self.client = client

    def request_payment(
        self, *, order_number: str, total: Decimal, currency: str,
        customer_id: str, payment_method_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = PaymentRequest(
            reference=order_number, amount=total, currency=currency,
            customer_id=customer_id, payment_method_id=payment_method_id,
            metadata=metadata,
        )
        return self.client.request_payment(request)
