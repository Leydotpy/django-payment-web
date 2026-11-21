from __future__ import annotations

from functools import lru_cache

from flutterwave_sdk import FlutterwaveClient

from .settings import get_payment_settings


@lru_cache(maxsize=1)
def get_flutterwave_client() -> FlutterwaveClient:
    settings = get_payment_settings()
    return FlutterwaveClient(
        client_id=settings.flutterwave_client_id,
        client_secret=settings.flutterwave_client_secret,
        encryption_key=settings.flutterwave_encryption_key,
        environment=settings.flutterwave_environment,
        timeout=settings.service_timeout_seconds,
        max_network_retries=settings.max_network_retries,
    )
