from __future__ import annotations

from celery import shared_task
from .domain import PaymentProcessor
from .schemas import PaymentChargeCommand


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def process_charge(self, payload: dict[str, object]) -> str:
    command = PaymentChargeCommand.model_validate(payload)
    intent = PaymentProcessor().process_charge(command)
    return str(intent.id)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=5)
def verify_payment(self, intent_id: str) -> str:
    return str(PaymentProcessor().verify_intent(intent_id=intent_id).id)
