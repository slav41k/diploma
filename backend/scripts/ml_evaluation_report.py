"""
Build reproducible ML evaluation artifacts for diploma section 4.

Outputs:
- backend/reports/ml_eval/metrics_summary.csv
- backend/reports/ml_eval/classification_report.txt
- backend/reports/ml_eval/confusion_matrix.png
- backend/reports/ml_eval/roc_curves_ovr.png
- backend/reports/ml_eval/metrics_bar.png
- backend/reports/ml_eval/dataset_card.md
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlretrieve
import zipfile

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    auc,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import label_binarize


ISOT_DATASET_ZIP = (
    "https://onlineacademiccommunity.uvic.ca/isot/wp-content/uploads/sites/7295/2023/03/News-_dataset.zip"
)
FAKE_OR_REAL_CSV = (
    "https://raw.githubusercontent.com/lutzhamel/fake-news/master/data/fake_or_real_news.csv"
)


@dataclass(frozen=True)
class EvalArtifacts:
    base_dir: Path
    data_dir: Path
    report_dir: Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    artifacts = EvalArtifacts(
        base_dir=root,
        data_dir=root / "data" / "external",
        report_dir=root / "reports" / "ml_eval",
    )
    artifacts.data_dir.mkdir(parents=True, exist_ok=True)
    artifacts.report_dir.mkdir(parents=True, exist_ok=True)

    df = load_dataset(artifacts)
    X_train, X_test, y_train, y_test = train_test_split(
        df["text"],
        df["label"],
        test_size=0.2,
        random_state=42,
        stratify=df["label"],
    )

    models = {
        "RandomForest": Pipeline(
            [
                ("tfidf", TfidfVectorizer(max_features=30_000, ngram_range=(1, 2))),
                (
                    "clf",
                    RandomForestClassifier(
                        n_estimators=300,
                        random_state=42,
                        class_weight="balanced",
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "LogisticRegression": Pipeline(
            [
                ("tfidf", TfidfVectorizer(max_features=30_000, ngram_range=(1, 2))),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                    ),
                ),
            ]
        ),
    }

    rows: list[dict[str, float | str]] = []
    trained_models: dict[str, Pipeline] = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        trained_models[name] = model
        pred = model.predict(X_test)
        rows.append(
            {
                "model": name,
                "accuracy": accuracy_score(y_test, pred),
                "precision_macro": precision_score(
                    y_test, pred, average="macro", zero_division=0
                ),
                "recall_macro": recall_score(
                    y_test, pred, average="macro", zero_division=0
                ),
                "f1_macro": f1_score(y_test, pred, average="macro", zero_division=0),
                "precision_weighted": precision_score(
                    y_test, pred, average="weighted", zero_division=0
                ),
                "recall_weighted": recall_score(
                    y_test, pred, average="weighted", zero_division=0
                ),
                "f1_weighted": f1_score(
                    y_test, pred, average="weighted", zero_division=0
                ),
            }
        )

    metrics_df = pd.DataFrame(rows).sort_values("f1_macro", ascending=False)
    metrics_df.to_csv(artifacts.report_dir / "metrics_summary.csv", index=False)
    plot_metrics_bar(metrics_df, artifacts.report_dir / "metrics_bar.png")

    best_name = str(metrics_df.iloc[0]["model"])
    best_model = trained_models[best_name]
    y_pred = best_model.predict(X_test)
    (artifacts.report_dir / "classification_report.txt").write_text(
        f"Best model: {best_name}\n\n"
        + classification_report(y_test, y_pred, digits=4, zero_division=0),
        encoding="utf-8",
    )
    save_confusion_matrix(
        y_test,
        y_pred,
        artifacts.report_dir / "confusion_matrix.png",
        title=f"Confusion Matrix ({best_name})",
    )
    save_roc_ovr(
        best_model,
        X_test,
        y_test,
        artifacts.report_dir / "roc_curves_ovr.png",
        title=f"ROC Curves (One-vs-Rest, {best_name})",
    )
    write_dataset_card(df, artifacts, best_name)

    print(f"Saved evaluation artifacts to: {artifacts.report_dir}")


def load_dataset(artifacts: EvalArtifacts) -> pd.DataFrame:
    fake_path = artifacts.data_dir / "fake_news_fake.csv"
    real_path = artifacts.data_dir / "fake_news_true.csv"
    isot_ready = fake_path.exists() and real_path.exists()
    if not isot_ready:
        try:
            download_and_extract_isot(artifacts, fake_path, real_path)
            isot_ready = True
        except Exception:
            isot_ready = False

    if not isot_ready:
        return load_fallback_fake_or_real(artifacts)

    fake = pd.read_csv(fake_path)
    real = pd.read_csv(real_path)

    fake = fake[["title", "text"]].copy()
    real = real[["title", "text"]].copy()
    fake["label"] = "bot_propaganda"
    real["label"] = "human_clean"

    df = pd.concat([fake, real], ignore_index=True)
    df["text"] = (
        df["title"].fillna("").astype(str) + ". " + df["text"].fillna("").astype(str)
    ).str.strip()
    df = df[df["text"].str.len() > 30].copy()
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
    return df


def download_and_extract_isot(
    artifacts: EvalArtifacts, fake_path: Path, real_path: Path
) -> None:
    zip_path = artifacts.data_dir / "isot_news_dataset.zip"
    if not zip_path.exists():
        urlretrieve(ISOT_DATASET_ZIP, zip_path)
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = {m.filename.lower(): m.filename for m in zf.infolist()}
        fake_member = next(
            (members[k] for k in members if k.endswith("/fake.csv") or k == "fake.csv"),
            None,
        )
        real_member = next(
            (members[k] for k in members if k.endswith("/true.csv") or k == "true.csv"),
            None,
        )
        if not fake_member or not real_member:
            raise RuntimeError("Could not find Fake.csv and True.csv in ISOT archive.")
        with zf.open(fake_member) as src:
            fake_path.write_bytes(src.read())
        with zf.open(real_member) as src:
            real_path.write_bytes(src.read())


def load_fallback_fake_or_real(artifacts: EvalArtifacts) -> pd.DataFrame:
    csv_path = artifacts.data_dir / "fake_or_real_news.csv"
    if not csv_path.exists():
        urlretrieve(FAKE_OR_REAL_CSV, csv_path)
    raw = pd.read_csv(csv_path)
    # Expected columns in this public dataset: title, text, label
    cols = {c.lower(): c for c in raw.columns}
    title_col = cols.get("title")
    text_col = cols.get("text")
    label_col = cols.get("label")
    if not title_col or not text_col or not label_col:
        raise RuntimeError("Unsupported schema for fake_or_real_news.csv")

    df = raw[[title_col, text_col, label_col]].copy()
    df.columns = ["title", "text", "label"]
    df["label"] = df["label"].astype(str).str.strip().str.lower().map(
        {"fake": "bot_propaganda", "real": "human_clean"}
    )
    df = df[df["label"].isin(["bot_propaganda", "human_clean"])].copy()
    df["text"] = (
        df["title"].fillna("").astype(str) + ". " + df["text"].fillna("").astype(str)
    ).str.strip()
    df = df[df["text"].str.len() > 30].copy()
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
    return df


def plot_metrics_bar(metrics_df: pd.DataFrame, out_path: Path) -> None:
    plot_df = metrics_df.melt(
        id_vars=["model"],
        value_vars=["accuracy", "precision_macro", "recall_macro", "f1_macro"],
        var_name="metric",
        value_name="score",
    )
    plt.figure(figsize=(10, 5))
    sns.barplot(data=plot_df, x="metric", y="score", hue="model")
    plt.ylim(0, 1.0)
    plt.title("Model quality metrics")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200)
    plt.close()


def save_confusion_matrix(
    y_true: pd.Series, y_pred: pd.Series, out_path: Path, title: str
) -> None:
    labels = sorted(set(y_true))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    plt.figure(figsize=(6, 5))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    disp.plot(cmap="Blues", values_format="d", colorbar=False)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def save_roc_ovr(
    model: Pipeline,
    X_test: pd.Series,
    y_test: pd.Series,
    out_path: Path,
    title: str,
) -> None:
    classes = sorted(set(y_test))
    y_bin = label_binarize(y_test, classes=classes)

    # Reuse trained text representation for ROC with one-vs-rest
    tfidf = model.named_steps["tfidf"]
    X_vec = tfidf.transform(X_test)
    ovr = OneVsRestClassifier(LogisticRegression(max_iter=2000))
    ovr.fit(X_vec, y_test)
    y_score = ovr.predict_proba(X_vec)

    plt.figure(figsize=(7, 6))
    if len(classes) == 2:
        # Binary case: roc_curve expects single target column
        pos_cls = classes[1]
        y_true_bin = (y_test == pos_cls).astype(int).to_numpy()
        pos_idx = int(list(ovr.classes_).index(pos_cls))
        fpr, tpr, _ = roc_curve(y_true_bin, y_score[:, pos_idx])
        roc_auc = auc(fpr, tpr)
        plt.plot(fpr, tpr, lw=2, label=f"{pos_cls} vs rest (AUC={roc_auc:.3f})")
    else:
        for i, cls in enumerate(classes):
            fpr, tpr, _ = roc_curve(y_bin[:, i], y_score[:, i])
            roc_auc = auc(fpr, tpr)
            plt.plot(fpr, tpr, lw=2, label=f"{cls} (AUC={roc_auc:.3f})")
    plt.plot([0, 1], [0, 1], linestyle="--", color="gray")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title(title)
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()


def write_dataset_card(df: pd.DataFrame, artifacts: EvalArtifacts, best_model: str) -> None:
    out_path = artifacts.report_dir / "dataset_card.md"
    sample_size = len(df)
    counts = df["label"].value_counts().to_dict()
    out_path.write_text(
        "\n".join(
            [
                "# Dataset card for diploma ML evaluation",
                "",
                "## Sources",
                f"- ISOT News dataset ZIP: {ISOT_DATASET_ZIP}",
                "- Extracted files from archive: `Fake.csv`, `True.csv`",
                f"- Fallback dataset (if ISOT unavailable): {FAKE_OR_REAL_CSV}",
                "",
                "## Processing",
                "- Combined `title + text` into one field `text`.",
                "- Labels mapped:",
                "  - fake -> bot_propaganda",
                "  - true -> human_clean",
                "- Removed short rows (`len(text) <= 30`).",
                "- Train/test split: 80/20, stratified.",
                "",
                "## Snapshot",
                f"- Rows used: {sample_size}",
                f"- Label distribution: `{json.dumps(counts, ensure_ascii=False)}`",
                f"- Best model by macro F1: `{best_model}`",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
