from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import httpx
import pika

from flutterwave_sdk import encrypt_card_details


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    reference: str
    amount: Decimal
    currency: str
    customer: dict[str, Any]
    encrypted_card: dict[str, str]
    redirect_url: str | None = None
    metadata: dict[str, Any] | None = None
    scenario_key: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "amount": str(self.amount),
            "currency": self.currency.upper(),
            "customer": self.customer,
            "encrypted_card": self.encrypted_card,
            "redirect_url": self.redirect_url,
            "metadata": self.metadata or {},
            "scenario_key": self.scenario_key,
        }


class PaymentMicroserviceClient:
    """Client that an Oscar/accounts-style commerce app can use.

    REST is useful for synchronous control-plane operations. RabbitMQ/Kafka is better for
    asynchronous payment processing at scale, especially where the checkout should not wait
    for provider latency.
    """

    def __init__(
        self,
        *,
        mode: Literal["rest", "rabbitmq"] = "rest",
        rest_base_url: str = "http://localhost:8000/api",
        rest_token: str | None = None,
        rabbitmq_url: str = "amqp://guest:guest@localhost:5672/%2F",
        command_queue: str = "payments.commands",
        timeout: float = 15.0,
    ) -> None:
        self.mode = mode
        self.rest_base_url = rest_base_url.rstrip("/")
        self.rest_token = rest_token
        self.rabbitmq_url = rabbitmq_url
        self.command_queue = command_queue
        self.timeout = timeout

    def request_card_payment(self, request: PaymentRequest) -> dict[str, Any]:
        if self.mode == "rabbitmq":
            self._publish_rabbitmq(request)
            return {"accepted": True, "reference": request.reference, "mode": "rabbitmq"}
        return self._post_rest(request)

    def _post_rest(self, request: PaymentRequest) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.rest_token:
            headers["Authorization"] = f"Bearer {self.rest_token}"
        response = httpx.post(
            f"{self.rest_base_url}/payment-intents/card-charge/",
            json=request.to_payload(),
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def _publish_rabbitmq(self, request: PaymentRequest) -> None:
        connection = pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))
        try:
            channel = connection.channel()
            channel.queue_declare(queue=self.command_queue, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=self.command_queue,
                body=json.dumps(request.to_payload(), default=str).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=request.reference,
                ),
            )
        finally:
            connection.close()


def build_encrypted_card_payment_request(
    *,
    reference: str,
    amount: Decimal,
    currency: str,
    customer: dict[str, Any],
    card_number: str,
    expiry_month: str | int,
    expiry_year: str | int,
    cvv: str,
    encryption_key: str,
    redirect_url: str | None = None,
    metadata: dict[str, Any] | None = None,
    scenario_key: str | None = None,
) -> PaymentRequest:
    encrypted_card = encrypt_card_details(
        card_number=card_number,
        expiry_month=expiry_month,
        expiry_year=expiry_year,
        cvv=cvv,
        encryption_key=encryption_key,
    )
    return PaymentRequest(
        reference=reference,
        amount=amount,
        currency=currency,
        customer=customer,
        encrypted_card=encrypted_card,
        redirect_url=redirect_url,
        metadata=metadata,
        scenario_key=scenario_key,
    )
