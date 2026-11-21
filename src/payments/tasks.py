from __future__ import annotations

from celery import shared_task

from .domain import PaymentProcessor
from .schemas import CardChargeCommand


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def process_card_charge(self, payload: dict[str, object]) -> str:
    command = CardChargeCommand.model_validate(payload)
    intent = PaymentProcessor().process_card_charge(command)
    return str(intent.id)
