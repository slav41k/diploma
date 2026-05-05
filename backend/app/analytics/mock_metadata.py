"""Синтетичні поведінкові ознаки Tier 1 (MVP без реального скрапінгу профілю Telegram).

``account_age_days`` — зміщений розподіл: більшість «дорослі» акаунти (100+ днів),
рідко <10 (новий акаунт / ризик бота), помірно 10–100 (підозрілий діапазон).
"""

from __future__ import annotations

import hashlib
import math
from typing import Any

import numpy as np


def _stable_seed(key: str) -> int:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(h[:12], 16) % (2**31)


def _slot_mod_15(label_key: str) -> int:
    """Детермінований слот 0..14 для стабільного «кожен 15-й» користувач."""
    return int(hashlib.sha256(label_key.encode("utf-8")).hexdigest(), 16) % 15


def sample_account_age_days(rng: np.random.RandomState) -> float:
    """Правдоподібний вік акаунта (дні): переважно 100+, рідко <10.

    Змішана модель: ~6% «нові» (<10), ~14% середні (10–100), ~80% старі (100–4000).
    """
    u = float(rng.random())
    if u < 0.06:
        return float(rng.uniform(1.0, 9.99))
    if u < 0.20:
        return float(rng.uniform(10.0, 99.99))
    return float(rng.uniform(100.0, 4000.0))


def sample_account_age_days_for_user(label_key: str, rng: np.random.RandomState) -> float:
    """Вік акаунта: рівно кожен 15-й user (за хешем id) потрапляє в 0–100 днів (новий або «молодий»)."""
    if _slot_mod_15(label_key) != 0:
        return sample_account_age_days(rng)
    # Піддіапазон теж детермінований: половина <10, половина 10–100
    flip = int(hashlib.sha256((label_key + "|age_segment").encode("utf-8")).hexdigest(), 16) % 2
    if flip == 0:
        return float(rng.uniform(1.0, 9.99))
    return float(rng.uniform(10.0, 99.99))


def account_age_band_from_days(age: float) -> str:
    """Ключі для UI: new_account | young_account | established."""
    if age < 10.0:
        return "new_account"
    if age < 100.0:
        return "young_account"
    return "established"


def enrich_with_mock_metadata(post: dict[str, Any]) -> dict[str, Any]:
    """Додає до ``metadata`` синтетичні поведінкові фічі (детерміновано від user id).

    Викликати з колектора після отримання реального коментаря або з пайплайну для mock.
    """
    meta = dict(post.get("metadata") or {})
    uid = meta.get("telegram_user_id")
    tag = meta.get("telegram_username") or meta.get("telegram_tag")
    label_key = (
        str(uid)
        if uid is not None
        else str(tag or post.get("user_id") or "anonymous")
    )
    rng = np.random.RandomState(_stable_seed(label_key))

    account_age_days = sample_account_age_days_for_user(label_key, rng)
    # Нові акаунти трохи частіше «шумні» за активністю (для RF), старі — спокійніші
    if account_age_days < 10.0:
        posts_per_hour = float(min(rng.exponential(10.0), 80.0))
    elif account_age_days < 100.0:
        posts_per_hour = float(min(rng.exponential(5.5), 80.0))
    else:
        posts_per_hour = float(min(rng.exponential(3.0), 80.0))

    follower_ratio = float(rng.beta(1.5, 4.0))
    followers_bucket = int(rng.randint(5, 500_000))

    display = str(meta.get("telegram_display_name") or post.get("user_id") or "")
    username_entropy = _char_entropy(display if len(display) > 1 else label_key)

    meta["account_age_days"] = round(account_age_days, 2)
    meta["account_age_band"] = account_age_band_from_days(account_age_days)
    meta["posts_per_hour"] = round(posts_per_hour, 4)
    meta["follower_ratio"] = round(follower_ratio, 6)
    meta["followers_bucket"] = followers_bucket
    meta["username_entropy"] = round(username_entropy, 6)
    meta["mock_behavior_tier1"] = True
    meta["tier1_enriched_at_source"] = True
    return meta


def enrich_mock_metadata(post: dict[str, Any]) -> dict[str, Any]:
    """Зворотна сумісність — те саме, що ``enrich_with_mock_metadata``."""
    return enrich_with_mock_metadata(post)


def merge_enriched_metadata(post: dict[str, Any]) -> dict[str, Any]:
    """Копія поста з enriched metadata."""
    out = dict(post)
    out["metadata"] = enrich_with_mock_metadata(post)
    return out


def merge_enriched_metadata_if_needed(post: dict[str, Any]) -> dict[str, Any]:
    """Не дублює збагачення, якщо вже є після колектора (Telegram)."""
    meta = post.get("metadata") or {}
    if meta.get("mock_behavior_tier1") and meta.get("account_age_days") is not None:
        return dict(post)
    return merge_enriched_metadata(post)


def _char_entropy(s: str) -> float:
    if not s:
        return 0.35
    freq: dict[str, int] = {}
    for ch in s.lower():
        freq[ch] = freq.get(ch, 0) + 1
    n = len(s)
    h = 0.0
    for c in freq.values():
        p = c / n
        h -= p * math.log2(p)
    return min(h / 6.0, 1.0)
