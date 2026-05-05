"""Статичний blacklist: небезпечні URL (новини) + окремо Telegram-користувачі в коментарях."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_BLACKLIST = _PACKAGE_ROOT / "data" / "blacklist.json"


def _load_blacklist() -> dict:
    path = _DEFAULT_BLACKLIST
    if not path.is_file():
        logger.warning("blacklist.json not found at %s", path)
        return {"urls": [], "telegram_users": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load blacklist")
        return {"urls": [], "telegram_users": []}


def reload_blacklist_cache() -> None:
    """Залишено для сумісності; файл читається щоразу без кешу."""


def _normalize_url(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "", s)
    return s


def is_source_url_blacklisted(target: str) -> bool:
    """Повний блок аналізу (наприклад зловмисний URL статті в urls)."""
    if not (target or "").strip():
        return False
    raw = _normalize_url(str(target))
    data = _load_blacklist()
    for u in data.get("urls") or []:
        uu = _normalize_url(str(u))
        if uu and uu in raw:
            return True
    return False


def is_telegram_user_blacklisted(ml_row: dict[str, Any]) -> bool:
    """Один рядок результатів ML (поля з telegram_* / user_id) у чорному списку користувачів."""
    data = _load_blacklist()
    entries = data.get("telegram_users") or []

    if not entries:
        return False

    uname = (ml_row.get("telegram_username") or "").strip().lstrip("@").lower()
    tag = (ml_row.get("telegram_tag") or "").strip().lstrip("@").lower()
    uid = ml_row.get("telegram_user_id")
    uid_str = str(uid).strip() if uid is not None else ""
    legacy_uid = str(ml_row.get("user_id") or "").strip()

    for raw in entries:
        e = str(raw).strip()
        if not e:
            continue
        if e.isdigit():
            if uid_str == e:
                return True
            continue
        el = e.lstrip("@").lower()
        if uname == el or tag == el:
            return True
        lu = legacy_uid.lstrip("@").lower()
        if lu == el:
            return True
        if legacy_uid.lower() == f"@{el}":
            return True

    return False
