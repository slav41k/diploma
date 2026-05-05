"""REST API (gateway): прийом запитів і публікація в Kafka analysis_requests."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.kafka.producer import KafkaProducerService
from app.schemas import AnalysisJobEnvelope, AnalysisQueuedResponse, AnalysisStartRequest
from app.storage.results import close_connection, get as get_result

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

producer = KafkaProducerService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await producer.start()
    yield
    await producer.stop()
    await close_connection()


app = FastAPI(
    title="Disinfo Detection API",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway", "kafka_client_id": producer.client_id}


@app.get("/")
async def root():
    return {
        "service": "gateway",
        "docs": "/docs",
        "start_analysis": "POST /api/v1/analysis/start",
        "poll_result": "GET /api/v1/analysis/{job_id}/result",
    }


@app.get("/api/v1/analysis/{job_id}/result")
async def analysis_result(job_id: UUID) -> dict[str, Any]:
    """Поллінг результату аналітики (мікросервіс зберігає у пам’яті після обробки raw_data)."""
    data = await get_result(str(job_id))
    if data is None:
        return {"status": "pending", "job_id": str(job_id)}
    return data


@app.post("/api/v1/analysis/start", response_model=AnalysisQueuedResponse)
async def start_analysis(body: AnalysisStartRequest):
    settings = get_settings()
    envelope = AnalysisJobEnvelope.from_request(body)
    payload = envelope.model_dump_kafka()
    try:
        await producer.send_json(
            settings.kafka_topic_analysis_requests,
            payload,
            key=str(envelope.job_id),
        )
    except Exception as exc:
        logger.exception("Kafka publish failed")
        raise HTTPException(
            status_code=503,
            detail=f"Не вдалося записати подію в Kafka: {exc}",
        ) from exc
    return AnalysisQueuedResponse(
        job_id=envelope.job_id,
        topic=settings.kafka_topic_analysis_requests,
    )
