from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pandas as pd


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def download_fred_series(series_id: str, output_path: Path) -> pd.DataFrame:
    """Download a FRED series as CSV and save it to disk.

    This script is intentionally simple and defensive. If the environment cannot
    resolve the remote host, the function raises a clear error and leaves the
    caller to handle it.
    """
    url = f"https://fred.stlouisfed.org/series/{series_id}/downloaddata/{series_id}.csv"
    try:
        df = pd.read_csv(url)
    except Exception as exc:
        raise RuntimeError(f"Failed to download FRED series {series_id} from {url}: {exc}") from exc

    df.to_csv(output_path, index=False)
    return df


def main() -> None:
    series_id = "DEXKOUS"
    raw_path = RAW_DIR / f"{series_id}.csv"
    processed_path = PROCESSED_DIR / f"{series_id}_processed.csv"

    df = download_fred_series(series_id, raw_path)

    if df.empty:
        raise RuntimeError("Downloaded data frame is empty")

    if "DATE" in df.columns and "VALUE" in df.columns:
        df = df.rename(columns={"DATE": "date", "VALUE": "usd_krw_krw_per_usd"})
    else:
        raise RuntimeError(f"Unexpected FRED columns: {df.columns.tolist()}")

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df.to_csv(processed_path, index=False)

    print(f"Saved raw data to: {raw_path}")
    print(f"Saved processed data to: {processed_path}")
    print(df.head())


if __name__ == "__main__":
    main()
