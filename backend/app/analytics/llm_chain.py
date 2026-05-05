"""LangChain + LLM (Groq / Gemini / OpenAI): Tier 2 + in-context «RAG» для MVP."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.config import Settings

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REF_PATH = _PACKAGE_ROOT / "data" / "reference_narratives.json"


class NarrativeLLMResult(BaseModel):
    threat_level: str = Field(
        description="Загальний рівень загрози англійською: low | medium | high",
    )
    summary_uk: str = Field(description="Короткий висновок українською.")
    risks: list[str] = Field(
        default_factory=list,
        description="Перелік ризиків або червоних прапорців.",
    )
    detail_json: str = Field(
        default="{}",
        description='Валідний JSON-рядок: переліки цитат, підозрілих формулювань, наративів.',
    )


_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Ти аналітик інформаційної безпеки. Оцінюй тексти на предмет дезінформації, "
            "пропаганди та ознак автоматизованих мереж. Поле detail_json має бути компактним JSON "
            "без markdown та без переносів поза рядком. Зіставляй зразки типових наративів нижче як орієнтири, "
            "не як фактичну базу.",
        ),
        (
            "human",
            "Контекст збору:\n{context}\n\n"
            "Типові патерни наративів (in-context reference, MVP без векторної БД):\n{reference_narratives}\n\n"
            "Тексти / фрагменти:\n{corpus}\n\n"
            "Підсумки ML Tier 1:\n{ml_digest}",
        ),
    ]
)


def _load_reference_narratives_block() -> str:
    if not _REF_PATH.is_file():
        return "(немає reference_narratives.json)"
    try:
        data = json.loads(_REF_PATH.read_text(encoding="utf-8"))
        lines: list[str] = []
        for n in data.get("narratives", []):
            nid = n.get("id", "?")
            summ = n.get("summary", "")
            lines.append(f"• [{nid}] {summ}")
        return "\n".join(lines) if lines else "(порожній список)"
    except Exception:
        logger.exception("reference_narratives load failed")
        return "(помилка завантаження)"


def _fallback_llm(is_news: bool, ml_digest: str, corpus: str) -> NarrativeLLMResult:
    snippet = corpus[:400].replace("\n", " ")
    detail = {
        "mode": "fallback",
        "is_news": is_news,
        "ml_digest": ml_digest[:2000],
        "snippet": snippet[:400],
        "note": (
            "Додайте безкоштовний ключ: GROQ_API_KEY (langchain-groq) або GOOGLE_API_KEY "
            "(Gemini), або OPENAI_API_KEY. LLM_PROVIDER=groq|gemini|openai|auto."
        ),
    }
    return NarrativeLLMResult(
        threat_level="medium",
        summary_uk=(
            "LLM недоступний: немає ключів або помилка виклику. Евристичний чернетковий висновок (MVP)."
        ),
        risks=["llm_unavailable"],
        detail_json=json.dumps(detail, ensure_ascii=False),
    )


def _build_chat_llm(settings: Settings):
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        ChatOpenAI = None  # type: ignore
    try:
        from langchain_groq import ChatGroq
    except ImportError:
        ChatGroq = None  # type: ignore
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        ChatGoogleGenerativeAI = None  # type: ignore

    p = (settings.llm_provider or "auto").lower()
    if p == "auto":
        if settings.groq_api_key and ChatGroq:
            p = "groq"
        elif settings.google_api_key and ChatGoogleGenerativeAI:
            p = "gemini"
        elif settings.openai_api_key and ChatOpenAI:
            p = "openai"
        else:
            p = ""

    if p == "groq" and settings.groq_api_key and ChatGroq:
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.2,
        )
    if p == "gemini" and settings.google_api_key and ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.google_api_key,
            temperature=0.2,
        )
    if p == "openai" and settings.openai_api_key and ChatOpenAI:
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=0.2,
        )

    if settings.groq_api_key and ChatGroq:
        return ChatGroq(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=0.2,
        )
    if settings.google_api_key and ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.google_api_key,
            temperature=0.2,
        )
    if settings.openai_api_key and ChatOpenAI:
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=0.2,
        )
    return None


def run_narrative_analysis(
    *,
    settings: Settings,
    corpus: str,
    ml_digest: str,
    context_lines: list[str],
    is_news: bool,
) -> NarrativeLLMResult:
    llm = _build_chat_llm(settings)
    if llm is None:
        return _fallback_llm(is_news, ml_digest, corpus)

    structured = llm.with_structured_output(NarrativeLLMResult)
    chain = _PROMPT | structured
    ctx = "\n".join(context_lines)
    ref_block = _load_reference_narratives_block()
    try:
        result = chain.invoke(
            {
                "context": ctx,
                "corpus": corpus[:48_000],
                "ml_digest": ml_digest[:12_000],
                "reference_narratives": ref_block,
            }
        )
        if isinstance(result, NarrativeLLMResult):
            return result
        if isinstance(result, dict):
            return NarrativeLLMResult.model_validate(result)
        return NarrativeLLMResult.model_validate(json.loads(str(result)))
    except Exception:
        logger.exception("LLM invocation failed; using fallback")
        return _fallback_llm(is_news, ml_digest, corpus)


def narrative_to_ui_json(result: NarrativeLLMResult) -> dict[str, Any]:
    try:
        detail = json.loads(result.detail_json or "{}")
    except json.JSONDecodeError:
        detail = {"raw_detail_json": result.detail_json}
    return {
        "threat_level": result.threat_level,
        "summary_uk": result.summary_uk,
        "risks": result.risks,
        "detail": detail,
    }
