from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw" / "fred"
DEFAULT_START_WEEK = "2014-12-15"
DEFAULT_END_WEEK = "2017-01-02"
RELEASE_DATE_PATTERN = re.compile(r"Release Date:\s*([^<]+)</div>", re.IGNORECASE)


def build_weekly_release_url(date: pd.Timestamp) -> str:
    return f"https://www.federalreserve.gov/releases/h15/{date:%Y%m%d}/"


def fetch_optional_weekly_release(url: str) -> bytes | None:
    request = Request(url, headers={"User-Agent": "fx-chronos/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"H.15 주간판 HTTP 상태가 200이 아닙니다: {response.status}")
            return response.read()
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"H.15 주간판 HTTP 오류가 발생했습니다: status={exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("H.15 주간판 요청에 실패했습니다. 네트워크를 확인하세요.") from exc


def parse_weekly_release_date(raw_bytes: bytes) -> pd.Timestamp:
    try:
        html = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("H.15 주간판 HTML을 UTF-8로 해석할 수 없습니다.") from exc
    match = RELEASE_DATE_PATTERN.search(html)
    if match is None:
        raise RuntimeError("H.15 주간판에서 Release Date를 찾지 못했습니다.")
    text = " ".join(match.group(1).split())
    try:
        parsed = datetime.strptime(text, "%B %d, %Y")
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"H.15 주간판 Release Date를 해석할 수 없습니다: {text}") from exc
    return pd.Timestamp(parsed.date())


def iter_week_starts(start_week: str, end_week: str) -> list[pd.Timestamp]:
    start = pd.Timestamp(start_week)
    end = pd.Timestamp(end_week)
    if start.weekday() != 0 or end.weekday() != 0:
        raise ValueError("H.15 주간판 시작일과 종료일은 월요일이어야 합니다.")
    if start > end:
        raise ValueError("H.15 주간판 시작주는 종료주보다 늦을 수 없습니다.")
    return list(pd.date_range(start, end, freq="W-MON"))


def find_weekly_release(
    week_start: pd.Timestamp,
    fetcher: Callable[[str], bytes | None] = fetch_optional_weekly_release,
) -> tuple[pd.Timestamp, bytes, str]:
    """Find the official release from Monday through Friday of one release week."""
    for offset in range(5):
        candidate = week_start + pd.Timedelta(days=offset)
        url = build_weekly_release_url(candidate)
        raw_bytes = fetcher(url)
        if raw_bytes is None:
            continue
        release_date = parse_weekly_release_date(raw_bytes)
        if not (week_start <= release_date <= week_start + pd.Timedelta(days=4)):
            raise RuntimeError(
                f"H.15 Release Date가 요청 주를 벗어났습니다: 주={week_start.date()}, "
                f"URL={candidate.date()}, 응답={release_date.date()}"
            )
        return release_date, raw_bytes, url
    raise RuntimeError(f"해당 주의 H.15 공식 주간판을 찾지 못했습니다: {week_start.date()}")


def collect_weekly_releases(
    week_starts: list[pd.Timestamp],
    fetcher: Callable[[str], bytes | None] = fetch_optional_weekly_release,
    max_workers: int = 4,
) -> dict[str, tuple[pd.Timestamp, bytes, str]]:
    if not week_starts:
        raise ValueError("수집할 H.15 주간판 주가 없습니다.")
    results: dict[str, tuple[pd.Timestamp, bytes, str]] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(find_weekly_release, week, fetcher): f"{week:%Y-%m-%d}"
            for week in week_starts
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                failures.append(f"{key}: {type(exc).__name__}")
    if failures:
        raise RuntimeError(f"H.15 주간판 수집 실패: {', '.join(sorted(failures))}")
    if len(results) != len(week_starts):
        raise RuntimeError("H.15 주간판 수집 결과에 누락이 있습니다.")
    return dict(sorted(results.items()))


def build_weekly_archive(
    releases: dict[str, tuple[pd.Timestamp, bytes, str]],
) -> tuple[bytes, list[dict[str, object]], pd.DatetimeIndex]:
    archive_buffer = BytesIO()
    manifest_rows: list[dict[str, object]] = []
    release_dates: list[pd.Timestamp] = []
    with ZipFile(archive_buffer, "w", compression=ZIP_DEFLATED) as archive:
        for week_start, (release_date, raw_bytes, url) in sorted(releases.items()):
            archive_name = f"{release_date:%Y-%m-%d}.html"
            archive.writestr(archive_name, raw_bytes)
            release_dates.append(release_date)
            manifest_rows.append(
                {
                    "week_start": week_start,
                    "release_date": release_date.date().isoformat(),
                    "source_url": url,
                    "archive_name": archive_name,
                    "byte_count": len(raw_bytes),
                    "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                    "availability_regime": (
                        "pre-2017 weekly Monday release; Tuesday after Monday holiday"
                    ),
                }
            )
    dates = pd.DatetimeIndex(release_dates).sort_values()
    if dates.empty or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise RuntimeError("H.15 주간판 공개일이 비었거나 중복됐거나 정렬되지 않았습니다.")
    return archive_buffer.getvalue(), manifest_rows, dates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="2017년 이전 H.15 공식 주간판을 수집합니다.")
    parser.add_argument("--start-week", default=DEFAULT_START_WEEK)
    parser.add_argument("--end-week", default=DEFAULT_END_WEEK)
    parser.add_argument("--max-workers", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    weeks = iter_week_starts(args.start_week, args.end_week)
    releases = collect_weekly_releases(weeks, max_workers=args.max_workers)
    archive_bytes, manifest_rows, release_dates = build_weekly_archive(releases)
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    period = f"{weeks[0]:%Y%m%d}_{weeks[-1]:%Y%m%d}"
    archive_path = RAW_DIR / f"h15_weekly_releases_{period}_{timestamp}.zip"
    manifest_path = RAW_DIR / f"h15_weekly_releases_{period}_{timestamp}_manifest.json"
    if archive_path.exists() or manifest_path.exists():
        raise FileExistsError("기존 H.15 주간판 스냅샷을 덮어쓰지 않습니다.")
    manifest = {
        "start_week": args.start_week,
        "end_week": args.end_week,
        "week_count": len(weeks),
        "release_count": len(release_dates),
        "first_release_date": release_dates.min().date().isoformat(),
        "last_release_date": release_dates.max().date().isoformat(),
        "collected_at_utc": collected_at.isoformat(),
        "availability_time_policy": (
            "exact historical posting time not encoded; use conservative end-of-release-day"
        ),
        "files": manifest_rows,
    }
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive_bytes)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"요청 주 범위: {args.start_week}~{args.end_week}")
    print(f"공식 주간판 수: {len(release_dates)}")
    print(f"최초 공식 공개일: {release_dates.min().date()}")
    print(f"최종 공식 공개일: {release_dates.max().date()}")
    print(f"원본 ZIP: {archive_path}")
    print(f"검증 manifest: {manifest_path}")


if __name__ == "__main__":
    main()
