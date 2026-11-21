from __future__ import annotations

import json
from typing import Any, Protocol

from .inline import InlineCommandBus
from .kafka import KafkaCommandBus
from .rabbitmq import RabbitMQCommandBus
from ..settings import get_payment_settings


class CommandBus(Protocol):
    def publish(self, *, key: str, payload: dict[str, Any]) -> None: ...


def get_command_bus() -> CommandBus:
    settings = get_payment_settings()
    if settings.broker_backend == "inline":
        return InlineCommandBus()
    if settings.broker_backend == "kafka":
        return KafkaCommandBus(settings.kafka_bootstrap_servers, settings.kafka_command_topic)
    # Celery and RabbitMQ both publish to RabbitMQ in this simple adapter. Celery workers can
    # alternatively call the task directly from the REST layer.
    return RabbitMQCommandBus(settings.rabbitmq_url, settings.rabbitmq_command_queue)


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
