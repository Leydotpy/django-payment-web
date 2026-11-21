from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class PaymentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PAYMENTS_", extra="ignore")

    flutterwave_client_id: str
    flutterwave_client_secret: str
    flutterwave_encryption_key: str
    flutterwave_environment: Literal["sandbox", "production"] = "sandbox"
    flutterwave_webhook_secret: str = ""

    broker_backend: Literal["celery", "rabbitmq", "kafka", "inline"] = "celery"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/%2F"
    rabbitmq_command_queue: str = "payments.commands"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_command_topic: str = "payments.commands"
    event_topic: str = "payments.events"

    service_timeout_seconds: float = 30.0
    max_network_retries: int = 2


@lru_cache(maxsize=1)
def get_payment_settings() -> PaymentSettings:
    return PaymentSettings()
