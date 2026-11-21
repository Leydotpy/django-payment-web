from __future__ import annotations

import json
from typing import Any

from aiokafka import AIOKafkaProducer
import asyncio


class KafkaCommandBus:
    """Small synchronous facade over aiokafka for web-request code paths."""

    def __init__(self, bootstrap_servers: str, topic: str) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic

    def publish(self, *, key: str, payload: dict[str, Any]) -> None:
        asyncio.run(self._publish(key=key, payload=payload))

    async def _publish(self, *, key: str, payload: dict[str, Any]) -> None:
        producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await producer.start()
        try:
            await producer.send_and_wait(
                self.topic,
                key=key.encode("utf-8"),
                value=json.dumps(payload, default=str).encode("utf-8"),
            )
        finally:
            await producer.stop()
