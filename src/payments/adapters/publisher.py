from __future__ import annotations

import asyncio
import json
from typing import Any

import pika
from aiokafka import AIOKafkaProducer

from ..settings import get_payment_settings


class MessagePublisher:
    """Publishes arbitrary JSON messages to RabbitMQ queues or Kafka topics."""

    def publish(self, *, topic: str, key: str, payload: dict[str, Any]) -> None:
        settings = get_payment_settings()
        if settings.broker_backend == "kafka":
            asyncio.run(self._publish_kafka(topic=topic, key=key, payload=payload))
            return
        self._publish_rabbitmq(queue=topic, key=key, payload=payload)

    def _publish_rabbitmq(self, *, queue: str, key: str, payload: dict[str, Any]) -> None:
        settings = get_payment_settings()
        connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
        try:
            channel = connection.channel()
            channel.queue_declare(queue=queue, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=queue,
                body=json.dumps(payload, default=str).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=key,
                ),
            )
        finally:
            connection.close()

    async def _publish_kafka(self, *, topic: str, key: str, payload: dict[str, Any]) -> None:
        settings = get_payment_settings()
        producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
        await producer.start()
        try:
            await producer.send_and_wait(
                topic,
                key=key.encode("utf-8"),
                value=json.dumps(payload, default=str).encode("utf-8"),
            )
        finally:
            await producer.stop()
