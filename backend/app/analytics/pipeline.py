"""Збір Random Forest + LLM у фінальний результат для UI та сховища."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.analytics.llm_chain import narrative_to_ui_json, run_narrative_analysis
from app.analytics.mock_metadata import merge_enriched_metadata_if_needed
from app.analytics.ml_rf import score_items
from app.analytics.threat_intel import (
    is_source_url_blacklisted,
    is_telegram_user_blacklisted,
)
from app.analytics.word_triggers import find_categorized_trigger_hits
from app.config import get_settings

logger = logging.getLogger(__name__)

_VERDICT_META = {
    "human_clean": {"label": "Людина/Чисто", "emoji": "🟢"},
    "suspicious": {"label": "Підозріло", "emoji": "🟡"},
    "bot_propaganda": {"label": "Бот/Пропаганда", "emoji": "🔴"},
}


def _threat_to_verdict(threat: str) -> dict[str, str]:
    t = (threat or "").lower()
    if "high" in t:
        return _VERDICT_META["bot_propaganda"]
    if "medium" in t:
        return _VERDICT_META["suspicious"]
    return _VERDICT_META["human_clean"]


def _blacklist_result(
    *,
    job_id: str,
    platform: Any,
    is_news: bool,
    items: list[dict[str, Any]],
    target: str,
) -> dict[str, Any]:
    bot = _VERDICT_META["bot_propaganda"]
    ui_users: list[dict[str, Any]] = []
    ml_items: list[dict[str, Any]] = []
    for it in items:
        meta = it.get("metadata") or {}
        entry: dict[str, Any] = {
            "user_id": it.get("user_id"),
            "verdict": bot["label"],
            "emoji": bot["emoji"],
            "source": "blacklist",
            "preview": (it.get("text") or "")[:280],
        }
        if meta.get("telegram_tag") is not None:
            entry["telegram_tag"] = meta["telegram_tag"]
        if meta.get("telegram_user_id") is not None:
            entry["telegram_user_id"] = meta["telegram_user_id"]
        if meta.get("telegram_display_name"):
            entry["telegram_display_name"] = meta["telegram_display_name"]
        ui_users.append(entry)
        ml_items.append(
            {
                "user_id": it.get("user_id"),
                "text_preview": (it.get("text") or "")[:280],
                "rf_skipped": True,
                "rf_label": None,
                "skip_reason": "blacklist",
            }
        )
    return {
        "status": "completed",
        "job_id": job_id,
        "platform": platform,
        "is_news": is_news,
        "blacklist_hit": True,
        "threat_level": "high",
        "users": ui_users,
        "ml_items": ml_items,
        "llm": {
            "threat_level": "high",
            "summary_uk": (
                "Джерело збігається з локальним чорним списком (Threat Intelligence MVP). "
                "Tier 1 (Random Forest) не застосовувався."
            ),
            "risks": ["blacklist_match"],
            "detail": {
                "mode": "blacklist_url",
                "target": target,
                "note": "Поле urls у blacklist.json — повна загроза без ML.",
            },
        },
    }


def process_raw_payload(raw: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    job_id = str(raw.get("job_id", ""))
    items = list(raw.get("items") or [])
    is_news = bool(raw.get("is_news"))
    platform = raw.get("platform")

    if (
        platform == "telegram"
        and len(items) == 1
        and (items[0].get("metadata") or {}).get("error") == "telegram_env_missing"
    ):
        hint = (items[0].get("text") or "").strip()
        return {
            "status": "completed",
            "job_id": job_id,
            "platform": platform,
            "is_news": False,
            "configuration_error": True,
            "threat_level": "not_applicable",
            "users": [
                {
                    "user_id": "Telegram API",
                    "verdict": "Не налаштовано (див. .env.example)",
                    "emoji": "⚙️",
                    "preview": hint[:800],
                    "source": "collector",
                }
            ],
            "ml_items": [],
            "llm": {
                "threat_level": "not_applicable",
                "summary_uk": (
                    "Збір з Telegram увімкнеться після додавання TELEGRAM_API_ID, "
                    "TELEGRAM_API_HASH і TELEGRAM_SESSION_STRING у файл .env у корені проєкту "
                    "та перезапуску контейнера collector."
                ),
                "risks": ["telegram_credentials_missing"],
                "detail": {
                    "steps": [
                        "Скопіюйте .env.example → .env",
                        "Заповніть api_id / api_hash з https://my.telegram.org",
                        "Запустіть: cd backend && python scripts/telegram_session.py",
                        "Вставте TELEGRAM_SESSION_STRING у .env",
                        "docker compose up -d --build collector",
                    ],
                },
            },
        }

    target = str(raw.get("target") or raw.get("article_url") or "").strip()
    if is_source_url_blacklisted(target):
        return _blacklist_result(
            job_id=job_id,
            platform=platform,
            is_news=is_news,
            items=items,
            target=target,
        )

    items = [merge_enriched_metadata_if_needed(it) for it in items]

    ml_scored = score_items(items, is_news=is_news)

    if not is_news:
        for idx, row in enumerate(ml_scored):
            body = items[idx].get("text") or ""
            cat_hits = find_categorized_trigger_hits(body)
            if cat_hits:
                row["rf_label"] = "bot_propaganda"
                row["rf_class"] = 2
                row["rf_bot_probability"] = max(
                    float(row.get("rf_bot_probability") or 0.0),
                    0.99,
                )
                row["trigger_category_hits"] = cat_hits
                row["trigger_words_hit"] = [
                    p for h in cat_hits for p in h.get("matched_phrases") or []
                ]

    blacklist_users_hit = False
    for row in ml_scored:
        if is_telegram_user_blacklisted(row):
            blacklist_users_hit = True
            row["rf_label"] = "bot_propaganda"
            row["rf_class"] = 2
            row["rf_bot_probability"] = 1.0
            row["blacklist_user"] = True

    corpus_parts: list[str] = []
    for i, it in enumerate(items):
        meta = it.get("metadata") or {}
        uid = meta.get("telegram_tag") or it.get("user_id")
        body = it.get("text") or ""
        corpus_parts.append(f"[{i}] {uid}: {body[:4000]}")
    corpus = "\n".join(corpus_parts)

    ml_lines = [
        json.dumps(
            {k: v for k, v in row.items() if k != "text_preview"},
            ensure_ascii=False,
        )
        for row in ml_scored
    ]
    ml_digest = "\n".join(ml_lines)

    context_lines = [
        f"platform={platform}",
        f"is_news={is_news}",
        f"items_count={len(items)}",
        f"blacklist_users_hit={blacklist_users_hit}",
    ]

    llm = run_narrative_analysis(
        settings=settings,
        corpus=corpus,
        ml_digest=ml_digest,
        context_lines=context_lines,
        is_news=is_news,
    )
    llm_block = narrative_to_ui_json(llm)

    ui_users: list[dict[str, Any]] = []
    if is_news and ml_scored:
        v = _threat_to_verdict(llm.threat_level)
        ui_users.append(
            {
                "user_id": ml_scored[0].get("user_id"),
                "verdict": v["label"],
                "emoji": v["emoji"],
                "source": "llm_threat_mapping",
                "preview": ml_scored[0].get("text_preview"),
            }
        )
    else:
        for row in ml_scored:
            label_key = row.get("rf_label") or "suspicious"
            meta = _VERDICT_META.get(label_key, _VERDICT_META["suspicious"])
            if row.get("blacklist_user"):
                src = "blacklist_user"
            elif row.get("trigger_category_hits"):
                src = "trigger_phrases"
            else:
                src = "random_forest"
            entry: dict[str, Any] = {
                "user_id": row.get("user_id"),
                "verdict": meta["label"],
                "emoji": meta["emoji"],
                "source": src,
                "rf_label": row.get("rf_label"),
                "rf_bot_probability": row.get("rf_bot_probability"),
                "preview": row.get("text_preview"),
            }
            if row.get("telegram_tag") is not None:
                entry["telegram_tag"] = row["telegram_tag"]
            if row.get("telegram_user_id") is not None:
                entry["telegram_user_id"] = row["telegram_user_id"]
            if row.get("telegram_display_name"):
                entry["telegram_display_name"] = row["telegram_display_name"]
            if row.get("account_age_days") is not None:
                entry["account_age_days"] = row["account_age_days"]
            if row.get("tier1_synthetic"):
                entry["tier1_synthetic"] = True
            if row.get("account_age_band"):
                entry["account_age_band"] = row["account_age_band"]
            reasons: list[str] = []
            if row.get("blacklist_user"):
                reasons.append(
                    "Червоний статус: користувач у локальному чорному списку "
                    "(backend/app/data/blacklist.json → telegram_users)."
                )
            tcat = row.get("trigger_category_hits")
            if tcat:
                for block in tcat:
                    h = str(block.get("heading") or "").strip()
                    d = str(block.get("detail") or "").strip()
                    phrases = block.get("matched_phrases") or []
                    pf = ", ".join(str(x) for x in phrases)
                    reasons.append(
                        "Червоний статус — "
                        + h
                        + (" — " + d if d else "")
                        + (". Збіги в тексті: " + pf if pf else "")
                    )
            elif row.get("trigger_words_hit"):
                tw = row.get("trigger_words_hit")
                reasons.append(
                    "Червоний статус: у тексті коментаря знайдено тригер(и) з word_triggers.json: "
                    + ", ".join(str(x) for x in tw)
                )
            if reasons:
                entry["verdict_reasons"] = reasons
            ui_users.append(entry)

    out: dict[str, Any] = {
        "status": "completed",
        "job_id": job_id,
        "platform": platform,
        "is_news": is_news,
        "threat_level": llm_block.get("threat_level"),
        "users": ui_users,
        "ml_items": ml_scored,
        "llm": llm_block,
    }
    if blacklist_users_hit:
        out["blacklist_users_hit"] = True
    return out
