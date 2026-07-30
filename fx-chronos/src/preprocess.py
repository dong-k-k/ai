from __future__ import annotations

import pandas as pd
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw" / "ecos"


def load_series(csv_path: Path) -> pd.Series:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df[["date", "value"]].copy()
    df = df.dropna()
    df = df.set_index("date")
    return df["value"]


def build_training_series(csv_path: Path) -> pd.Series:
    series = load_series(csv_path)
    return series.astype(float)


def save_preprocessed_series(series: pd.Series, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    series.to_frame(name="value").to_csv(out_path, index=True)


def main() -> None:
    input_path = PROCESSED_DIR / "usd_krw_krw_per_usd.csv"
    output_path = PROCESSED_DIR / "usd_krw_preprocessed.csv"
    series = build_training_series(input_path)
    save_preprocessed_series(series, output_path)
    print(f"Saved preprocessed series to {output_path}")
    print(series.head())


if __name__ == "__main__":
    main()
