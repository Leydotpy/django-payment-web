from __future__ import annotations

import json

import pika
from django.core.management.base import BaseCommand

from payments.domain import PaymentProcessor
from payments.schemas import CardChargeCommand
from payments.settings import get_payment_settings


class Command(BaseCommand):
    help = "Consume payment commands from RabbitMQ and process them."

    def handle(self, *args, **options):
        settings = get_payment_settings()
        connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
        channel = connection.channel()
        channel.queue_declare(queue=settings.rabbitmq_command_queue, durable=True)
        channel.basic_qos(prefetch_count=8)
        processor = PaymentProcessor()

        def callback(ch, method, properties, body):
            try:
                payload = json.loads(body.decode("utf-8"))
                command = CardChargeCommand.model_validate(payload)
                processor.process_card_charge(command)
            except Exception as exc:  # noqa: BLE001 - worker boundary must not crash the channel
                self.stderr.write(self.style.ERROR(f"Payment command failed: {exc}"))
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            else:
                ch.basic_ack(delivery_tag=method.delivery_tag)

        channel.basic_consume(queue=settings.rabbitmq_command_queue, on_message_callback=callback)
        self.stdout.write(self.style.SUCCESS("RabbitMQ payment consumer started."))
        try:
            channel.start_consuming()
        finally:
            connection.close()
