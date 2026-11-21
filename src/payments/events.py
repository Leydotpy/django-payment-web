"""Durable events and commands written atomically with Django payment state."""
from __future__ import annotations

from broka.envelope import Envelope
from broka.integrations.django.outbox import DjangoModelOutboxStore
from broka.reliability.outbox import OutboxMessage
from .models import PaymentOutboxRecord


def outbox_store() -> DjangoModelOutboxStore:
    return DjangoModelOutboxStore(PaymentOutboxRecord)


def queue_message(event_type: str, payload: dict, *, reference: str) -> None:
    """Call inside transaction.atomic(): the broker publish happens only after commit."""
    envelope = Envelope.create(payload, type=event_type, version=1)
    outbox_store().add_in_transaction(
        OutboxMessage(envelope=envelope, destination=event_type, metadata={"reference": reference})
    )
