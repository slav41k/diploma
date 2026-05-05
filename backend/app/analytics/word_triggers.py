"""Тригер-фрази за категоріями (data/word_triggers.json)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PATH = _PACKAGE_ROOT / "data" / "word_triggers.json"


def _load_raw() -> dict[str, Any]:
    path = _DEFAULT_PATH
    if not path.is_file():
        logger.warning("word_triggers.json not found at %s", path)
        return {"categories": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load word_triggers.json")
        return {"categories": []}


def find_categorized_trigger_hits(text: str) -> list[dict[str, Any]]:
    """Збіги по категоріях: heading, detail і конкретні фрази з тексту.

    Повертає список об'єктів з ключами: id, heading, detail, matched_phrases.
    """
    data = _load_raw()
    categories = data.get("categories") or []
    raw = (text or "").strip()
    if not raw:
        return []

    lower = raw.lower()
    results: list[dict[str, Any]] = []

    for cat in categories:
        cid = str(cat.get("id") or "").strip()
        heading = str(cat.get("heading") or "").strip()
        detail = str(cat.get("detail") or "").strip()
        phrases = [
            str(p).strip()
            for p in (cat.get("phrases") or [])
            if str(p).strip()
        ]
        matched: list[str] = []
        seen_lower: set[str] = set()

        for ph in sorted(phrases, key=len, reverse=True):
            pl = ph.lower()
            if pl in seen_lower:
                continue
            if pl in lower:
                matched.append(ph)
                seen_lower.add(pl)

        if cid == "emotional_triggers":
            if _matches_urgent_exclamations(raw) and not any(
                "терміново" in (m or "").lower() for m in matched
            ):
                tag = "терміново… (багато знаків оклику)"
                tl = tag.lower()
                if tl not in seen_lower:
                    matched.append(tag)
                    seen_lower.add(tl)

        matched = _drop_shorter_overlapping_phrases(matched)

        if matched:
            results.append(
                {
                    "id": cid,
                    "heading": heading,
                    "detail": detail,
                    "matched_phrases": matched,
                }
            )

    return results


def _drop_shorter_overlapping_phrases(phrases: list[str]) -> list[str]:
    """Якщо в тексті збіглись і «терміново!!!», і «терміново!!», лишаємо довшу форму."""
    if len(phrases) < 2:
        return phrases
    uniq = sorted(set(phrases), key=len, reverse=True)
    kept: list[str] = []
    for ph in uniq:
        pl = ph.lower()
        if any(pl in k.lower() for k in kept):
            continue
        kept.append(ph)
    return kept


def _matches_urgent_exclamations(text: str) -> bool:
    """«терміново» з двома й більше знаками оклику підряд (після слова або одразу)."""
    return bool(
        re.search(r"терміново\s*!{2,}", text, flags=re.IGNORECASE | re.UNICODE)
    )


def find_trigger_hits_in_comment(text: str) -> list[str]:
    """Плоский список збігів (для сумісності з ml_digest / полем trigger_words_hit)."""
    out: list[str] = []
    seen: set[str] = set()
    for block in find_categorized_trigger_hits(text):
        for p in block.get("matched_phrases") or []:
            pl = p.lower()
            if pl not in seen:
                seen.add(pl)
                out.append(p)
    return out
