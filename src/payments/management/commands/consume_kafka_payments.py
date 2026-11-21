from __future__ import annotations

import asyncio
import json

from aiokafka import AIOKafkaConsumer
from django.core.management.base import BaseCommand

from payments.domain import PaymentProcessor
from payments.schemas import CardChargeCommand
from payments.settings import get_payment_settings


class Command(BaseCommand):
    help = "Consume payment commands from Kafka and process them."

    def handle(self, *args, **options):
        asyncio.run(self._run())

    async def _run(self) -> None:
        settings = get_payment_settings()
        consumer = AIOKafkaConsumer(
            settings.kafka_command_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="payments-service",
            enable_auto_commit=False,
        )
        await consumer.start()
        processor = PaymentProcessor()
        self.stdout.write(self.style.SUCCESS("Kafka payment consumer started."))
        try:
            async for message in consumer:
                try:
                    payload = json.loads(message.value.decode("utf-8"))
                    processor.process_card_charge(CardChargeCommand.model_validate(payload))
                    await consumer.commit()
                except Exception as exc:  # noqa: BLE001 - worker boundary must continue
                    self.stderr.write(self.style.ERROR(f"Payment command failed: {exc}"))
        finally:
            await consumer.stop()
