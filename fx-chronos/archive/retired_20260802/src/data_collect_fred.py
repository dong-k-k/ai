from __future__ import annotations

import os
import json
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from io import BytesIO

import numpy as np
import pandas as pd


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

BROAD_USD_SERIES_ID = "DTWEXBGS"
BROAD_USD_UNIT = "Index Jan 2006=100"
BROAD_USD_FREQUENCY = "Daily"
BROAD_USD_START_DATE = "2024-01-01"
BROAD_USD_END_DATE = "2024-03-31"
DGS3_SERIES_ID = "DGS3"
DGS3_UNIT = "Percent"
DGS3_FREQUENCY = "Daily"
DGS3_START_DATE = "2024-07-01"
DGS3_END_DATE = "2024-07-10"
FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


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


def build_fred_graph_url(series_id: str, start_date: str, end_date: str) -> str:
    """기간을 제한한 FRED 공식 Graph CSV URL을 만든다."""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start > end:
        raise ValueError("FRED 시작일은 종료일보다 늦을 수 없습니다.")
    return f"{FRED_GRAPH_CSV_URL}?{urlencode({'id': series_id, 'cosd': start.date(), 'coed': end.date()})}"


def fetch_fred_csv(url: str) -> bytes:
    """API 키 없이 FRED CSV 원본 바이트를 내려받는다."""
    request = Request(url, headers={"User-Agent": "fx-chronos/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"FRED HTTP 상태가 200이 아닙니다: {response.status}")
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"FRED HTTP 오류가 발생했습니다: status={exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("FRED CSV 요청에 실패했습니다. 네트워크 연결을 확인하세요.") from exc


def process_fred_series_csv(
    raw_bytes: bytes,
    start_date: str,
    end_date: str,
    series_id: str,
    project_column_name: str,
    unit: str,
    frequency: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """원본 행을 삭제하지 않고 일별 FRED 시계열의 품질을 검사한다."""
    dataframe = pd.read_csv(BytesIO(raw_bytes), dtype=str, keep_default_na=False)
    expected_columns = ["observation_date", series_id]
    if dataframe.columns.tolist() != expected_columns:
        raise RuntimeError(
            f"FRED 응답 열이 예상과 다릅니다: 실제={dataframe.columns.tolist()}, "
            f"예상={expected_columns}"
        )
    if dataframe.empty:
        raise RuntimeError(f"FRED {series_id} 응답이 비어 있습니다.")

    parsed_dates = pd.to_datetime(dataframe["observation_date"], errors="coerce")
    raw_values = dataframe[series_id].str.strip()
    numeric_values = pd.to_numeric(raw_values, errors="coerce")
    empty_values = raw_values.eq("") | raw_values.eq(".")
    conversion_failures = (~empty_values) & numeric_values.isna()
    invalid_dates = parsed_dates.isna()
    duplicate_dates = parsed_dates.duplicated(keep=False) & ~invalid_dates
    outside_period = ~parsed_dates.between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    nonpositive_values = numeric_values.notna() & (numeric_values <= 0)

    if invalid_dates.any():
        raise RuntimeError(f"FRED 응답에 변환할 수 없는 날짜가 있습니다: {int(invalid_dates.sum())}건")
    if duplicate_dates.any():
        raise RuntimeError(f"FRED 응답에 중복 날짜가 있습니다: {int(duplicate_dates.sum())}행")
    if outside_period.any():
        raise RuntimeError(f"FRED 응답에 요청 기간 밖 날짜가 있습니다: {int(outside_period.sum())}건")
    if conversion_failures.any():
        raise RuntimeError(
            f"FRED 응답에 숫자로 변환할 수 없는 값이 있습니다: {int(conversion_failures.sum())}건"
        )
    if nonpositive_values.any():
        raise RuntimeError(f"FRED 응답에 0 이하 지수값이 있습니다: {int(nonpositive_values.sum())}건")

    processed = pd.DataFrame(
        {
            "date": parsed_dates,
            project_column_name: numeric_values,
            "series_id": series_id,
            "unit": unit,
            "frequency": frequency,
        }
    ).sort_values("date").reset_index(drop=True)
    finite_values = numeric_values[np.isfinite(numeric_values)]
    summary: dict[str, object] = {
        "requested_start": start_date,
        "requested_end": end_date,
        "raw_rows": len(dataframe),
        "processed_rows": len(processed),
        "first_date": processed["date"].min().date().isoformat(),
        "last_date": processed["date"].max().date().isoformat(),
        "duplicate_date_rows": int(duplicate_dates.sum()),
        "empty_value_rows": int(empty_values.sum()),
        "numeric_conversion_failures": int(conversion_failures.sum()),
        "outside_period_rows": int(outside_period.sum()),
        "nonpositive_value_rows": int(nonpositive_values.sum()),
        "minimum_value": float(finite_values.min()),
        "maximum_value": float(finite_values.max()),
        "dates_monotonic_increasing": bool(processed["date"].is_monotonic_increasing),
    }
    return processed, summary


def process_broad_usd_csv(
    raw_bytes: bytes,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """원본 행을 삭제하지 않고 Broad Dollar Index의 품질을 검사한다."""
    return process_fred_series_csv(
        raw_bytes,
        start_date,
        end_date,
        BROAD_USD_SERIES_ID,
        "broad_usd_index",
        BROAD_USD_UNIT,
        BROAD_USD_FREQUENCY,
    )


def process_dgs3_csv(
    raw_bytes: bytes,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """원본 행을 보존하며 미국 국채 3년물 수익률을 검사한다."""
    return process_fred_series_csv(
        raw_bytes,
        start_date,
        end_date,
        DGS3_SERIES_ID,
        "us_treasury_3y_percent",
        DGS3_UNIT,
        DGS3_FREQUENCY,
    )


def collect_broad_usd_short_period(
    start_date: str = BROAD_USD_START_DATE,
    end_date: str = BROAD_USD_END_DATE,
) -> tuple[Path, Path, Path, dict[str, object]]:
    """짧은 기간을 수집해 원본, 처리본, 메타데이터를 새 파일로 저장한다."""
    url = build_fred_graph_url(BROAD_USD_SERIES_ID, start_date, end_date)
    raw_bytes = fetch_fred_csv(url)
    processed, summary = process_broad_usd_csv(raw_bytes, start_date, end_date)
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    period = f"{pd.Timestamp(start_date):%Y%m%d}_{pd.Timestamp(end_date):%Y%m%d}"
    raw_path = RAW_DIR / "fred" / f"dtwexbgs_{period}_{timestamp}.csv"
    processed_path = PROCESSED_DIR / "fred" / f"broad_usd_index_{period}_{timestamp}.csv"
    metadata_path = RAW_DIR / "fred" / f"dtwexbgs_{period}_{timestamp}_metadata.json"
    output_paths = (raw_path, processed_path, metadata_path)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 FRED 수집 결과를 덮어쓰지 않습니다: {existing}")

    metadata = {
        "series_id": BROAD_USD_SERIES_ID,
        "series_name": "Nominal Broad U.S. Dollar Index",
        "project_column_name": "broad_usd_index",
        "unit": BROAD_USD_UNIT,
        "frequency": BROAD_USD_FREQUENCY,
        "seasonal_adjustment": "Not Seasonally Adjusted",
        "source": "Board of Governors of the Federal Reserve System (US)",
        "release": "H.10 Foreign Exchange Rates",
        "source_url": url,
        "collected_at_utc": collected_at.isoformat(),
        "availability_policy": "pending point-in-time release-date alignment; do not join by observation date",
        "quality_summary": summary,
    }
    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw_bytes)
    processed.to_csv(processed_path, index=False, date_format="%Y-%m-%d")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return raw_path, processed_path, metadata_path, summary


def collect_dgs3_short_period(
    start_date: str = DGS3_START_DATE,
    end_date: str = DGS3_END_DATE,
) -> tuple[Path, Path, Path, dict[str, object]]:
    """미국 국채 3년물의 짧은 기간 원본·처리본·메타데이터를 저장한다."""
    url = build_fred_graph_url(DGS3_SERIES_ID, start_date, end_date)
    raw_bytes = fetch_fred_csv(url)
    processed, summary = process_dgs3_csv(raw_bytes, start_date, end_date)
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    period = f"{pd.Timestamp(start_date):%Y%m%d}_{pd.Timestamp(end_date):%Y%m%d}"
    raw_path = RAW_DIR / "fred" / f"dgs3_{period}_{timestamp}.csv"
    processed_path = PROCESSED_DIR / "fred" / f"us_treasury_3y_{period}_{timestamp}.csv"
    metadata_path = RAW_DIR / "fred" / f"dgs3_{period}_{timestamp}_metadata.json"
    output_paths = (raw_path, processed_path, metadata_path)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 FRED 수집 결과를 덮어쓰지 않습니다: {existing}")

    metadata = {
        "series_id": DGS3_SERIES_ID,
        "series_name": (
            "Market Yield on U.S. Treasury Securities at 3-Year Constant Maturity, "
            "Quoted on an Investment Basis"
        ),
        "project_column_name": "us_treasury_3y_percent",
        "unit": DGS3_UNIT,
        "frequency": DGS3_FREQUENCY,
        "seasonal_adjustment": "Not Seasonally Adjusted",
        "source": "Board of Governors of the Federal Reserve System (US)",
        "release": "H.15 Selected Interest Rates",
        "source_url": url,
        "collected_at_utc": collected_at.isoformat(),
        "availability_policy": (
            "pending H.15 point-in-time alignment; do not join by observation date"
        ),
        "quality_summary": summary,
    }
    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(raw_bytes)
    processed.to_csv(processed_path, index=False, date_format="%Y-%m-%d")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return raw_path, processed_path, metadata_path, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FRED Broad Dollar Index를 기간별 수집합니다.")
    parser.add_argument("--start-date", default=BROAD_USD_START_DATE)
    parser.add_argument("--end-date", default=BROAD_USD_END_DATE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    url = build_fred_graph_url(
        BROAD_USD_SERIES_ID,
        args.start_date,
        args.end_date,
    )
    print(f"요청 URL: {url}")
    raw_path, processed_path, metadata_path, summary = collect_broad_usd_short_period(
        args.start_date,
        args.end_date,
    )
    print(f"요청 기간: {summary['requested_start']}~{summary['requested_end']}")
    print(f"원본 행 수: {summary['raw_rows']}")
    print(f"처리 행 수: {summary['processed_rows']}")
    print(f"최초 날짜: {summary['first_date']}")
    print(f"최종 날짜: {summary['last_date']}")
    print(f"중복 날짜 행 수: {summary['duplicate_date_rows']}")
    print(f"빈 값 행 수: {summary['empty_value_rows']}")
    print(f"숫자 변환 실패 수: {summary['numeric_conversion_failures']}")
    print(f"기간 밖 행 수: {summary['outside_period_rows']}")
    print(f"0 이하 값 수: {summary['nonpositive_value_rows']}")
    print(f"원본 저장 경로: {raw_path}")
    print(f"처리 저장 경로: {processed_path}")
    print(f"메타데이터 저장 경로: {metadata_path}")


if __name__ == "__main__":
    main()
