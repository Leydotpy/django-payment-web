from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    email: str
    name: dict[str, Any] | None = None
    phone: dict[str, Any] | None = None
    address: dict[str, Any] | None = None


class EncryptedCardPayload(BaseModel):
    nonce: str = Field(min_length=12, max_length=12)
    encrypted_card_number: str = Field(min_length=1)
    encrypted_expiry_month: str = Field(min_length=1)
    encrypted_expiry_year: str = Field(min_length=1)
    encrypted_cvv: str = Field(min_length=1)


class CardChargeCommand(BaseModel):
    """Broker command consumed by the payment service worker.

    Only encrypted card details should cross broker boundaries. This keeps RabbitMQ/Kafka
    payloads away from raw PAN/CVV data.
    """

    model_config = ConfigDict(extra="forbid")

    intent_id: UUID
    reference: str
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    customer: CustomerPayload
    encrypted_card: EncryptedCardPayload
    redirect_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    scenario_key: str | None = None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class CardChargeRequestedEvent(BaseModel):
    event_type: Literal["payment.card_charge.requested"] = "payment.card_charge.requested"
    intent_id: UUID
    reference: str
    amount: Decimal
    currency: str


class PaymentCompletedEvent(BaseModel):
    event_type: Literal["payment.completed"] = "payment.completed"
    intent_id: UUID
    reference: str
    provider_charge_id: str
    provider_status: str
    amount: Decimal
    currency: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentFailedEvent(BaseModel):
    event_type: Literal["payment.failed"] = "payment.failed"
    intent_id: UUID
    reference: str
    message: str
    code: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuthorizePinCommand(BaseModel):
    intent_id: UUID
    charge_id: str
    encrypted_pin: dict[str, str]
    scenario_key: str | None = None


class AuthorizeOtpCommand(BaseModel):
    intent_id: UUID
    charge_id: str
    otp: str
    scenario_key: str | None = None
