"""Мікросервіс аналітики: consumer `raw_data` → ML + LLM → збереження результату."""

from __future__ import annotations

import asyncio
import logging

from app.analytics.pipeline import process_raw_payload
from app.config import get_settings
from app.kafka.consumer import JsonKafkaConsumer
from app.storage.results import save

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    consumer = JsonKafkaConsumer(
        settings.kafka_topic_raw_data,
        group_id=settings.kafka_group_analytics,
    )
    await consumer.start()

    async def handle(payload: dict) -> None:
        job_id = str(payload.get("job_id", ""))
        result = await asyncio.to_thread(process_raw_payload, payload)
        await save(job_id, result)
        logger.info("Saved analytics result job_id=%s threat=%s", job_id, result.get("threat_level"))

    try:
        logger.info("Analytics listening on %s", settings.kafka_topic_raw_data)
        await consumer.consume_forever(handle)
    finally:
        await consumer.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
