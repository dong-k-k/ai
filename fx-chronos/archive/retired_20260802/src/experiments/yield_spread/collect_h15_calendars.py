from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from src.experiments.yield_spread.prepare_yield_spread_availability import (
    build_h15_calendar_url,
    fetch_h15_calendar,
    parse_h15_release_dates,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw" / "fred"
DEFAULT_START_MONTH = "2014-12"
DEFAULT_END_MONTH = "2022-01"
KNOWN_UNAVAILABLE_MONTHS = {
    "2019-09": "official Federal Reserve monthly calendar page returns 404",
}


def iter_months(start_month: str, end_month: str) -> list[pd.Timestamp]:
    start = pd.Timestamp(f"{start_month}-01")
    end = pd.Timestamp(f"{end_month}-01")
    if start > end:
        raise ValueError("H.15 달력 시작월은 종료월보다 늦을 수 없습니다.")
    return list(pd.date_range(start, end, freq="MS"))


def collect_calendar_payloads(
    months: list[pd.Timestamp],
    fetcher: Callable[[str], bytes] = fetch_h15_calendar,
    max_workers: int = 4,
    skip_months: set[str] | None = None,
) -> dict[str, bytes]:
    """Fetch every official month completely or fail without returning a partial set."""
    if not months:
        raise ValueError("수집할 H.15 달력 월이 없습니다.")
    if max_workers < 1:
        raise ValueError("max_workers는 1 이상이어야 합니다.")
    skipped = skip_months or set()
    urls = {
        f"{month:%Y-%m}": build_h15_calendar_url(month.year, month.month)
        for month in months
        if f"{month:%Y-%m}" not in skipped
    }
    unknown_skips = skipped - {f"{month:%Y-%m}" for month in months}
    if unknown_skips:
        raise ValueError(f"요청 범위 밖 H.15 달력 월을 제외할 수 없습니다: {sorted(unknown_skips)}")
    payloads: dict[str, bytes] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetcher, url): key for key, url in urls.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                payloads[key] = future.result()
            except Exception as exc:
                failures.append(f"{key}: {type(exc).__name__}")
    if failures:
        raise RuntimeError(f"H.15 월별 달력 수집 실패: {', '.join(sorted(failures))}")
    if set(payloads) != set(urls):
        raise RuntimeError("H.15 월별 달력 수집 결과에 누락이 있습니다.")
    return dict(sorted(payloads.items()))


def build_calendar_archive(
    payloads: dict[str, bytes],
) -> tuple[bytes, list[dict[str, object]], pd.DatetimeIndex]:
    """Validate each official calendar and package the unchanged HTML in one ZIP."""
    archive_buffer = BytesIO()
    manifest_rows: list[dict[str, object]] = []
    all_dates: list[pd.Timestamp] = []
    with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
        for month_key, raw_bytes in sorted(payloads.items()):
            month = pd.Timestamp(f"{month_key}-01")
            release_dates = parse_h15_release_dates(raw_bytes, month.year, month.month)
            archive_name = f"{month_key}.html"
            archive.writestr(archive_name, raw_bytes)
            all_dates.extend(pd.Timestamp(value) for value in release_dates)
            manifest_rows.append(
                {
                    "month": month_key,
                    "source_url": build_h15_calendar_url(month.year, month.month),
                    "archive_name": archive_name,
                    "byte_count": len(raw_bytes),
                    "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                    "release_date_count": len(release_dates),
                    "first_release_date": release_dates.min().date().isoformat(),
                    "last_release_date": release_dates.max().date().isoformat(),
                }
            )
    combined = pd.DatetimeIndex(all_dates).sort_values()
    if combined.empty or combined.duplicated().any():
        raise RuntimeError("통합 H.15 공개일이 비었거나 월간 파일 사이에 중복됐습니다.")
    if not combined.is_monotonic_increasing:
        raise RuntimeError("통합 H.15 공개일이 오름차순이 아닙니다.")
    return archive_buffer.getvalue(), manifest_rows, combined


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="연준 월별 H.15 공식 달력을 ZIP으로 수집합니다.")
    parser.add_argument("--start-month", default=DEFAULT_START_MONTH)
    parser.add_argument("--end-month", default=DEFAULT_END_MONTH)
    parser.add_argument("--max-workers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    months = iter_months(args.start_month, args.end_month)
    unavailable = {
        key: reason
        for key, reason in KNOWN_UNAVAILABLE_MONTHS.items()
        if months[0].strftime("%Y-%m") <= key <= months[-1].strftime("%Y-%m")
    }
    payloads = collect_calendar_payloads(
        months,
        max_workers=args.max_workers,
        skip_months=set(unavailable),
    )
    archive_bytes, manifest_rows, release_dates = build_calendar_archive(payloads)
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    period = f"{months[0]:%Y%m}_{months[-1]:%Y%m}"
    archive_path = RAW_DIR / f"h15_calendars_{period}_{timestamp}.zip"
    manifest_path = RAW_DIR / f"h15_calendars_{period}_{timestamp}_manifest.json"
    if archive_path.exists() or manifest_path.exists():
        raise FileExistsError("기존 H.15 달력 스냅샷을 덮어쓰지 않습니다.")
    manifest = {
        "start_month": args.start_month,
        "end_month": args.end_month,
        "requested_month_count": len(months),
        "archived_month_count": len(payloads),
        "unavailable_months": unavailable,
        "release_date_count": len(release_dates),
        "first_release_date": release_dates.min().date().isoformat(),
        "last_release_date": release_dates.max().date().isoformat(),
        "collected_at_utc": collected_at.isoformat(),
        "release_time_policy": "H.15 official calendar, 16:15 America/New_York",
        "files": manifest_rows,
    }
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_bytes)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"요청 월 범위: {args.start_month}~{args.end_month}")
    print(f"요청 월 수: {len(months)}")
    print(f"보존한 월별 공식 달력 수: {len(payloads)}")
    print(f"공식 달력 미확인 월 수: {len(unavailable)}")
    print(f"통합 H.15 공개일 수: {len(release_dates)}")
    print(f"최초 공개일: {release_dates.min().date()}")
    print(f"최종 공개일: {release_dates.max().date()}")
    print(f"원본 ZIP: {archive_path}")
    print(f"검증 manifest: {manifest_path}")


if __name__ == "__main__":
    main()
