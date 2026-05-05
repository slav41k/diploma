"""
Мікросервіс збору: consumer `analysis_requests` → producer `raw_data`.
Соцмережі — mock-дані; новинний портал — спроба парсингу через newspaper3k.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from newspaper import Article

from app.config import get_settings
from app.services.telegram_collect import collect_channel_comments
from app.kafka.consumer import JsonKafkaConsumer
from app.kafka.producer import KafkaProducerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def fetch_news_article(url: str) -> dict[str, Any]:
    article = Article(url)
    article.download()
    article.parse()
    text = (article.text or "").strip()
    if len(text) < 40:
        raise ValueError("Отримано надто короткий текст після парсингу")
    return {
        "title": article.title or "",
        "text": text,
        "authors": list(article.authors or []),
        "language": article.meta_lang or "",
    }


def _mock_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    platform = payload.get("platform", "unknown")
    mc = int(payload.get("message_count") or 10)
    mc = min(max(mc, 10), 100)
    n = min(mc, 25)
    return [
        {
            "user_id": f"user_{i}",
            "text": f"(mock) Повідомлення {i} для {platform}",
            "metadata": {"seq": i, "mock": True},
        }
        for i in range(1, n + 1)
    ]


async def build_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("platform") == "telegram":
        post_limit = int(payload.get("post_count") or 5)
        post_limit = min(max(post_limit, 1), 50)
        target = str(payload.get("target") or "").strip()
        return await collect_channel_comments(
            channel_hint=target,
            post_limit=post_limit,
        )

    if payload.get("platform") == "news_portal":
        url = str(payload.get("article_url") or "").strip()
        try:
            data = await asyncio.to_thread(fetch_news_article, url)
            return [
                {
                    "user_id": "article",
                    "text": data["text"],
                    "metadata": {
                        "title": data["title"],
                        "authors": data["authors"],
                        "language": data["language"],
                        "url": url,
                        "parser": "newspaper3k",
                    },
                }
            ]
        except Exception as exc:
            logger.exception("News parsing failed for url=%s", url)
            return [
                {
                    "user_id": "article",
                    "text": f"(помилка парсингу) {exc}",
                    "metadata": {
                        "error": str(exc),
                        "url": url,
                        "parser": "newspaper3k",
                    },
                }
            ]

    return _mock_items(payload)


async def run() -> None:
    settings = get_settings()
    producer = KafkaProducerService(client_id="collector-producer")
    await producer.start()

    consumer = JsonKafkaConsumer(
        settings.kafka_topic_analysis_requests,
        group_id=settings.kafka_group_collector,
    )
    await consumer.start()

    async def handle(payload: dict[str, Any]) -> None:
        job_id = str(payload.get("job_id", ""))
        items = await build_items(payload)
        raw_payload = {
            "job_id": payload.get("job_id"),
            "platform": payload.get("platform"),
            "is_news": payload.get("platform") == "news_portal",
            "requested_at": payload.get("requested_at"),
            "target": payload.get("target"),
            "article_url": payload.get("article_url"),
            "items": items,
        }
        await producer.send_json(
            settings.kafka_topic_raw_data,
            raw_payload,
            key=job_id or "unknown",
        )
        logger.info("Published raw_data for job_id=%s items=%s", job_id, len(items))

    try:
        logger.info("Collector listening on %s", settings.kafka_topic_analysis_requests)
        await consumer.consume_forever(handle)
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
