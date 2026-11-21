from __future__ import annotations

from decimal import Decimal
from typing import Any

from .client import PaymentMicroserviceClient, build_encrypted_card_payment_request


class FlutterwaveCheckoutBridge:
    """Integration point for an Oscar PaymentDetailsView-like checkout flow.

    In a real Oscar project, call `request_card_payment` from your customised
    `handle_payment(...)` method, then create Oscar Source/Transaction records from the
    returned PaymentIntent reference and final webhook event.
    """

    def __init__(self, *, client: PaymentMicroserviceClient, encryption_key: str) -> None:
        self.client = client
        self.encryption_key = encryption_key

    def request_card_payment(
        self,
        *,
        order_number: str,
        total: Decimal,
        currency: str,
        customer_email: str,
        card_number: str,
        expiry_month: str | int,
        expiry_year: str | int,
        cvv: str,
        redirect_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = build_encrypted_card_payment_request(
            reference=order_number,
            amount=total,
            currency=currency,
            customer={"email": customer_email},
            card_number=card_number,
            expiry_month=expiry_month,
            expiry_year=expiry_year,
            cvv=cvv,
            encryption_key=self.encryption_key,
            redirect_url=redirect_url,
            metadata=metadata,
        )
        return self.client.request_card_payment(request)
