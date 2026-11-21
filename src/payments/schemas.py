from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaymentChargeCommand(BaseModel):
    """Durable charge command: never transport PAN, CVV, encrypted CVV or authorisation secrets."""

    model_config = ConfigDict(extra="forbid")
    intent_id: UUID
    reference: str
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    customer_id: str = Field(min_length=1)
    payment_method_id: str = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class PaymentCompletedEvent(BaseModel):
    event_type: Literal["payment.completed"] = "payment.completed"
    intent_id: UUID
    reference: str
    provider_charge_id: str
    provider_status: str
    amount: Decimal
    currency: str
    verified: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentFailedEvent(BaseModel):
    event_type: Literal["payment.failed"] = "payment.failed"
    intent_id: UUID
    reference: str
    provider_charge_id: str = ""
    message: str
    code: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
