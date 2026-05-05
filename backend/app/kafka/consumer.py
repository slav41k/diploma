import json
import logging
from typing import Any, Awaitable, Callable, Optional

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _json_deserialize(raw: Optional[bytes]) -> Any:
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8"))


class JsonKafkaConsumer:
    """Базовий async consumer з JSON-десеріалізацією значень."""

    def __init__(
        self,
        *topics: str,
        group_id: str,
        settings: Optional[Settings] = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._topics = topics
        self._group_id = group_id
        self._consumer: Optional[AIOKafkaConsumer] = None

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            group_id=self._group_id,
            enable_auto_commit=True,
            auto_offset_reset="earliest",
            value_deserializer=_json_deserialize,
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
        )
        await self._consumer.start()
        logger.info(
            "Kafka consumer started topics=%s group=%s bootstrap=%s",
            self._topics,
            self._group_id,
            self._settings.kafka_bootstrap_servers,
        )

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
            logger.info("Kafka consumer stopped")

    async def consume_forever(
        self,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        if self._consumer is None:
            raise RuntimeError("Consumer is not started")
        try:
            async for msg in self._consumer:
                try:
                    if msg.value is None:
                        continue
                    await handler(msg.value)
                except Exception:
                    logger.exception("Handler failed for kafka message")
        except KafkaError:
            logger.exception("Kafka consumer loop error")
