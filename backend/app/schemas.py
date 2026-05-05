from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class Platform(str, Enum):
    telegram = "telegram"
    twitter = "twitter"
    reddit = "reddit"
    instagram = "instagram"
    facebook = "facebook"
    news_portal = "news_portal"


class AnalysisStartRequest(BaseModel):
    """Тіло запиту з Next.js для запуску моніторингу."""

    platform: Platform
    target: Optional[str] = Field(
        default=None,
        description="URL або username каналу / профілю",
    )
    message_count: Optional[int] = Field(
        default=None,
        ge=10,
        le=100,
        description="Кількість записів (інші соцмережі; не Telegram)",
    )
    post_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Скільки останніх постів каналу перевірити на коментарі (лише Telegram)",
    )
    article_url: Optional[str] = Field(
        default=None,
        description="URL статті для новинного порталу",
    )

    @model_validator(mode="after")
    def validate_news_vs_social(self) -> "AnalysisStartRequest":
        if self.platform == Platform.news_portal:
            if not self.article_url or not str(self.article_url).strip():
                raise ValueError("Для новинного порталу потрібне поле article_url")
            if self.target is not None or self.message_count is not None:
                raise ValueError("Для новин зайві поля target / message_count")
            if self.post_count is not None:
                raise ValueError("post_count лише для Telegram")
        elif self.platform == Platform.telegram:
            if not self.target or not str(self.target).strip():
                raise ValueError("Вкажіть посилання або @канал Telegram")
            if self.post_count is None:
                raise ValueError("Для Telegram потрібне поле post_count (1–50 останніх постів)")
            if self.message_count is not None:
                raise ValueError("Для Telegram використовуйте post_count, а не message_count")
            if self.article_url is not None:
                raise ValueError("article_url лише для новинного порталу")
        else:
            if not self.target or not str(self.target).strip():
                raise ValueError("Для соцмереж потрібне поле target")
            if self.message_count is None:
                raise ValueError("Для соцмереж потрібне поле message_count (10–100)")
            if self.post_count is not None:
                raise ValueError("post_count лише для Telegram")
            if self.article_url is not None:
                raise ValueError("article_url лише для новинного порталу")
        return self


class AnalysisJobEnvelope(BaseModel):
    """Повідомлення в топік analysis_requests (JSON)."""

    job_id: UUID
    platform: Platform
    target: Optional[str] = None
    message_count: Optional[int] = None
    post_count: Optional[int] = None
    article_url: Optional[str] = None
    requested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @classmethod
    def from_request(cls, body: AnalysisStartRequest) -> "AnalysisJobEnvelope":
        return cls(
            job_id=uuid4(),
            platform=body.platform,
            target=body.target,
            message_count=body.message_count,
            post_count=body.post_count,
            article_url=body.article_url,
        )

    def model_dump_kafka(self) -> dict:
        return self.model_dump(mode="json")


class AnalysisQueuedResponse(BaseModel):
    job_id: UUID
    status: str = "queued"
    topic: str
