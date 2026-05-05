"""
Random Forest (Tier 1): ознаки з enrich_mock_metadata — синтетичне навчання для PoC.

Модель навчається на правило-подібних синтетичних даних з тими ж вимірами,
що й інференс після enrich_mock_metadata().
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from app.analytics.mock_metadata import sample_account_age_days_for_user

logger = logging.getLogger(__name__)

_LABELS = ("human_clean", "suspicious", "bot_propaganda")


def _features(item: dict[str, Any]) -> np.ndarray:
    text = item.get("text") or ""
    meta = item.get("metadata") or {}
    age = float(meta.get("account_age_days") or 400.0)
    pph = float(meta.get("posts_per_hour") or 2.0)
    fr = float(meta.get("follower_ratio") or 0.5)
    ent = float(meta.get("username_entropy") or 0.55)
    fbuck = float(meta.get("followers_bucket") or 1000.0)
    seq = float(meta.get("seq", 0))
    mock = 1.0 if meta.get("mock") else 0.0
    err = 1.0 if meta.get("error") else 0.0

    return np.array(
        [
            min(max(age, 0.0), 8000.0) / 8000.0,
            min(max(pph, 0.0), 80.0) / 80.0,
            min(max(fr, 0.0), 1.0),
            min(max(ent, 0.0), 1.0),
            np.log1p(max(fbuck, 0.0)) / np.log1p(500_000.0),
            min(len(text), 10_000) / 1000.0,
            min(max(seq, 0.0), 100.0) / 100.0,
            mock,
            err,
        ],
        dtype=float,
    )


def _build_synthetic_training(n: int = 4000, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Ті самі зміщені ``account_age_days``, що й у enrich_with_mock_metadata; мітки узгоджені з діапазонами віку."""
    rng = np.random.RandomState(seed)
    X = np.zeros((n, 9), dtype=float)
    y = np.zeros(n, dtype=int)
    for i in range(n):
        age = float(sample_account_age_days_for_user(f"synth_train_{i}", rng))
        if age < 10.0:
            pph = float(min(rng.exponential(10.0), 80.0))
        elif age < 100.0:
            pph = float(min(rng.exponential(5.5), 80.0))
        else:
            pph = float(min(rng.exponential(3.0), 80.0))
        fr = float(rng.beta(1.5, 4.0))
        ent = float(rng.uniform(0.12, 1.0))
        fbuck = float(rng.uniform(20.0, 600_000.0))
        tl = float(rng.uniform(15.0, 8000.0))
        seq = float(rng.uniform(0.0, 99.0))
        mock = float(rng.randint(0, 2))
        err = float(rng.randint(0, 2))

        row = np.array(
            [
                min(age, 8000.0) / 8000.0,
                min(pph, 80.0) / 80.0,
                fr,
                ent,
                np.log1p(fbuck) / np.log1p(500_000.0),
                min(tl, 10_000.0) / 1000.0,
                seq / 100.0,
                mock,
                err,
            ],
            dtype=float,
        )
        X[i] = row

        # Помилка даних → підозріло
        if err > 0.5:
            label = 1
        # Новий акаунт (<10 д): прискорена активність / співвідношення → бот; інакше підозріло або чисто
        elif age < 10.0:
            if pph > 28.0 or fr > 0.88:
                label = 2
            elif pph > 16.0:
                label = 1
            else:
                label = 0
        # Середній вік (10–100): типово людина; крайні ознаки → підозріло / рідко бот
        elif age < 100.0:
            if pph > 38.0 or fr > 0.93 or ent < 0.28:
                label = 1
            elif pph > 48.0 and ent < 0.32:
                label = 2
            else:
                label = 0
        # Дорослий акаунт (100+): вік сам по собі не тягне вердикт «бот»
        else:
            if pph > 68.0 and fr > 0.94:
                label = 1
            elif pph > 78.0:
                label = 1
            else:
                label = 0
        y[i] = label

    return X, y


_X_TRAIN, _Y_TRAIN = _build_synthetic_training()
_model = RandomForestClassifier(
    n_estimators=80,
    max_depth=12,
    min_samples_leaf=4,
    random_state=42,
    class_weight="balanced",
)
_model.fit(_X_TRAIN, _Y_TRAIN)


def score_items(items: list[dict[str, Any]], is_news: bool) -> list[dict[str, Any]]:
    if is_news:
        return [
            {
                **_item_defaults(item),
                "rf_skipped": True,
                "rf_label": None,
                "rf_class": None,
            }
            for item in items
        ]

    out: list[dict[str, Any]] = []
    for item in items:
        X = _features(item).reshape(1, -1)
        cls = int(_model.predict(X)[0])
        proba = float(np.max(_model.predict_proba(X)))
        cls = cls % 3
        label = _LABELS[cls]
        out.append(
            {
                **_item_defaults(item),
                "rf_skipped": False,
                "rf_class": cls,
                "rf_label": label,
                "rf_bot_probability": round(proba, 4),
            }
        )
    return out


def _item_defaults(item: dict[str, Any]) -> dict[str, Any]:
    meta = item.get("metadata") or {}
    row: dict[str, Any] = {
        "user_id": item.get("user_id"),
        "text_preview": (item.get("text") or "")[:280],
    }
    if meta.get("telegram_tag") is not None:
        row["telegram_tag"] = meta.get("telegram_tag")
    if meta.get("telegram_user_id") is not None:
        row["telegram_user_id"] = meta.get("telegram_user_id")
    if meta.get("telegram_username") is not None:
        row["telegram_username"] = meta.get("telegram_username")
    if meta.get("telegram_display_name"):
        row["telegram_display_name"] = meta.get("telegram_display_name")
    if meta.get("account_age_days") is not None:
        row["account_age_days"] = meta.get("account_age_days")
    if meta.get("account_age_band"):
        row["account_age_band"] = meta.get("account_age_band")
    if meta.get("mock_behavior_tier1"):
        row["tier1_synthetic"] = True
    return row
