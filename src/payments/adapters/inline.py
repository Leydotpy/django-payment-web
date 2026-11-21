from __future__ import annotations

from typing import Any

from ..domain import PaymentProcessor
from ..schemas import CardChargeCommand


class InlineCommandBus:
    """Synchronous adapter useful for local development and tests."""

    def publish(self, *, key: str, payload: dict[str, Any]) -> None:
        PaymentProcessor().process_card_charge(CardChargeCommand.model_validate(payload))
