from __future__ import annotations

import json
from typing import Any

import pika


class RabbitMQCommandBus:
    """Publishes payment commands to RabbitMQ with durable messages."""

    def __init__(self, amqp_url: str, queue_name: str) -> None:
        self.amqp_url = amqp_url
        self.queue_name = queue_name

    def publish(self, *, key: str, payload: dict[str, Any]) -> None:
        parameters = pika.URLParameters(self.amqp_url)
        connection = pika.BlockingConnection(parameters)
        try:
            channel = connection.channel()
            channel.queue_declare(queue=self.queue_name, durable=True)
            channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=json.dumps(payload, default=str).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=key,
                ),
            )
        finally:
            connection.close()
