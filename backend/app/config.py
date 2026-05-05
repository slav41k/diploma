from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_analysis_requests: str = "analysis_requests"
    kafka_topic_raw_data: str = "raw_data"

    kafka_client_id_gateway: str = "gateway"
    kafka_group_collector: str = "collector-service"
    kafka_group_analytics: str = "analytics-service"

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # Tier 2 LLM: auto вибирає перший доступний ключ (groq → gemini → openai)
    llm_provider: str = "auto"
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.1-8b-instant"
    google_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash"

    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    telegram_session_string: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
