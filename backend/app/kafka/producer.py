import json
import logging
from typing import Any, Optional

from aiokafka import AIOKafkaProducer

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _json_serialize(value: Any) -> bytes:
    return json.dumps(value, default=str).encode("utf-8")


class KafkaProducerService:
    """Async producer для публікації подій у Kafka."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        client_id: Optional[str] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client_id = client_id or self._settings.kafka_client_id_gateway
        self._producer: Optional[AIOKafkaProducer] = None

    @property
    def client_id(self) -> str:
        return self._client_id

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=self._client_id,
            value_serializer=_json_serialize,
            key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
        )
        await self._producer.start()
        logger.info(
            "Kafka producer started (bootstrap=%s)",
            self._settings.kafka_bootstrap_servers,
        )

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
            logger.info("Kafka producer stopped")

    async def send_json(self, topic: str, payload: dict, key: str) -> None:
        if self._producer is None:
            raise RuntimeError("Producer is not started")
        await self._producer.send_and_wait(topic, value=payload, key=key)
