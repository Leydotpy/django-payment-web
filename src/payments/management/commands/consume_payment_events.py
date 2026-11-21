"""Run a dedicated Broka consumer process, not a Django web worker."""
from __future__ import annotations

import asyncio

from asgiref.sync import sync_to_async
from broka.integrations.django import get_broker
from dispio import Dispatcher
from dispio.integrations import BrokaDispatchBridge
from django.core.management.base import BaseCommand

from payments.domain import PaymentProcessor
from payments.schemas import PaymentChargeCommand


async def run_consumer() -> None:
    bridge = BrokaDispatchBridge(Dispatcher(name="payment-commands"))

    @bridge.on("payments.charge.requested")
    async def handle_charge(delivery):
        command = PaymentChargeCommand.model_validate(delivery.message)
        await sync_to_async(PaymentProcessor().process_charge, thread_sensitive=True)(command)

    @bridge.on("payments.webhook.received")
    async def handle_webhook(delivery):
        event_id = str(delivery.message["provider_event_id"])
        await sync_to_async(PaymentProcessor().process_webhook, thread_sensitive=True)(
            provider_event_id=event_id
        )

    @bridge.on("payments.verification.requested")
    async def handle_verification(delivery):
        intent_id = str(delivery.message["intent_id"])
        await sync_to_async(PaymentProcessor().verify_intent, thread_sensitive=True)(
            intent_id=intent_id
        )

    async with get_broker() as broker:
        await broker.subscribe("payments.charge.requested", bridge.dispatch_delivery)
        await broker.subscribe("payments.webhook.received", bridge.dispatch_delivery)
        await broker.subscribe("payments.verification.requested", bridge.dispatch_delivery)
        await asyncio.Event().wait()


class Command(BaseCommand):
    help = "Consume Broka payment commands and route them with Dispio."

    def handle(self, *args, **kwargs):
        try:
            asyncio.run(run_consumer())
        except KeyboardInterrupt:
            self.stdout.write("Payment event consumer stopped.")
