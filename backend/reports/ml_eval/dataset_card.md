# Dataset card for diploma ML evaluation

## Sources
- ISOT News dataset ZIP: https://onlineacademiccommunity.uvic.ca/isot/wp-content/uploads/sites/7295/2023/03/News-_dataset.zip
- Extracted files from archive: `Fake.csv`, `True.csv`
- Fallback dataset (if ISOT unavailable): https://raw.githubusercontent.com/lutzhamel/fake-news/master/data/fake_or_real_news.csv

## Processing
- Combined `title + text` into one field `text`.
- Labels mapped:
  - fake -> bot_propaganda
  - true -> human_clean
- Removed short rows (`len(text) <= 30`).
- Train/test split: 80/20, stratified.

## Snapshot
- Rows used: 6332
- Label distribution: `{"human_clean": 3171, "bot_propaganda": 3161}`
- Best model by macro F1: `LogisticRegression`