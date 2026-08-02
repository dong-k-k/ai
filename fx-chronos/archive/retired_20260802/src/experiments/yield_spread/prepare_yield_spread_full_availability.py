from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from src.experiments.yield_spread.prepare_yield_spread_availability import (
    NEW_YORK,
    SEOUL,
    assign_kr_yield_availability,
    parse_h15_release_dates,
    serialize_availability,
)


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
KR_INPUT_PATH = PROCESSED_DIR / "ecos" / "kr_treasury_3y_20141209_20211231.csv"
US_INPUT_PATH = (
    PROCESSED_DIR
    / "fred"
    / "us_treasury_3y_20141209_20211231_20260802T121957Z.csv"
)
WEEKLY_ARCHIVE_PATH = (
    PROJECT_DIR
    / "data"
    / "raw"
    / "fred"
    / "h15_weekly_releases_20141215_20160926_20260802T122733Z.zip"
)
WEEKLY_MANIFEST_PATH = WEEKLY_ARCHIVE_PATH.with_name(
    "h15_weekly_releases_20141215_20160926_20260802T122733Z_manifest.json"
)
DAILY_ARCHIVE_PATH = (
    PROJECT_DIR
    / "data"
    / "raw"
    / "fred"
    / "h15_calendars_201701_202201_20260802T122738Z.zip"
)
DAILY_MANIFEST_PATH = DAILY_ARCHIVE_PATH.with_name(
    "h15_calendars_201701_202201_20260802T122738Z_manifest.json"
)
WEEKLY_REGIME_END = pd.Timestamp("2016-09-26")
DAILY_REGIME_START = pd.Timestamp("2017-01-03")
TRANSITION_OBSERVATION_START = pd.Timestamp("2016-09-26")
TRANSITION_OBSERVATION_END = pd.Timestamp("2017-01-02")
MISSING_MONTH_START = pd.Timestamp("2019-09-01")
MISSING_MONTH_END = pd.Timestamp("2019-09-30")


def load_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"H.15 manifest를 읽을 수 없습니다: {path}") from exc
    if not isinstance(payload.get("files"), list) or not payload["files"]:
        raise RuntimeError(f"H.15 manifest 파일 목록이 비었습니다: {path}")
    return payload


def verify_archive_rows(
    archive: ZipFile,
    rows: list[dict[str, object]],
) -> dict[str, bytes]:
    expected_names = [str(row["archive_name"]) for row in rows]
    if sorted(archive.namelist()) != sorted(expected_names):
        raise RuntimeError("H.15 ZIP 파일 목록과 manifest가 일치하지 않습니다.")
    payloads: dict[str, bytes] = {}
    for row in rows:
        name = str(row["archive_name"])
        raw_bytes = archive.read(name)
        if len(raw_bytes) != int(row["byte_count"]):
            raise RuntimeError(f"H.15 원본 바이트 수가 manifest와 다릅니다: {name}")
        if hashlib.sha256(raw_bytes).hexdigest() != str(row["sha256"]):
            raise RuntimeError(f"H.15 원본 SHA-256이 manifest와 다릅니다: {name}")
        payloads[name] = raw_bytes
    return payloads


def load_weekly_release_dates(manifest_path: Path, archive_path: Path) -> pd.DatetimeIndex:
    manifest = load_manifest(manifest_path)
    rows = manifest["files"]
    with ZipFile(archive_path) as archive:
        verify_archive_rows(archive, rows)
    dates = pd.DatetimeIndex(
        pd.to_datetime([str(row["release_date"]) for row in rows], errors="raise")
    ).sort_values()
    if dates.duplicated().any() or dates.max() != WEEKLY_REGIME_END:
        raise RuntimeError("H.15 주간판 공개일이 중복됐거나 종료일이 예상과 다릅니다.")
    return dates


def load_daily_release_dates(manifest_path: Path, archive_path: Path) -> pd.DatetimeIndex:
    manifest = load_manifest(manifest_path)
    rows = manifest["files"]
    unavailable = manifest.get("unavailable_months", {})
    if unavailable != {
        "2019-09": "official Federal Reserve monthly calendar page returns 404"
    }:
        raise RuntimeError(f"H.15 공식 달력 미확인 월이 예상과 다릅니다: {unavailable}")
    all_dates: list[pd.Timestamp] = []
    with ZipFile(archive_path) as archive:
        payloads = verify_archive_rows(archive, rows)
    for row in rows:
        month_key = str(row["month"])
        month = pd.Timestamp(f"{month_key}-01")
        dates = parse_h15_release_dates(
            payloads[str(row["archive_name"])], month.year, month.month
        )
        if len(dates) != int(row["release_date_count"]):
            raise RuntimeError(f"H.15 월별 공개일 수가 manifest와 다릅니다: {month_key}")
        all_dates.extend(pd.Timestamp(value) for value in dates)
    combined = pd.DatetimeIndex(all_dates).sort_values()
    if combined.duplicated().any() or combined.min() != DAILY_REGIME_START:
        raise RuntimeError("H.15 일별 공개일이 중복됐거나 시작일이 예상과 다릅니다.")
    return combined


def assign_us_yield_full_availability(
    observations: pd.DataFrame,
    weekly_release_dates: pd.DatetimeIndex,
    daily_release_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    required = {"date", "us_treasury_3y_percent", "series_id", "unit", "frequency"}
    missing = required - set(observations.columns)
    if missing:
        raise RuntimeError(f"미국 3년물 처리본에 필수 열이 없습니다: {sorted(missing)}")
    output = observations.copy()
    output["date"] = pd.to_datetime(output["date"], errors="raise")
    if output["date"].duplicated().any() or not output["date"].is_monotonic_increasing:
        raise RuntimeError("미국 3년물 날짜가 중복됐거나 오름차순이 아닙니다.")
    if set(output["series_id"].astype(str)) != {"DGS3"}:
        raise RuntimeError("미국 3년물 series ID가 DGS3와 다릅니다.")
    if set(output["unit"].astype(str)) != {"Percent"}:
        raise RuntimeError("미국 3년물 단위가 Percent와 다릅니다.")

    combined_dates = weekly_release_dates.append(daily_release_dates).sort_values()
    if combined_dates.duplicated().any():
        raise RuntimeError("공개 체계 사이에 H.15 공개일 중복이 있습니다.")
    release_values: list[pd.Timestamp] = []
    available_et_values: list[datetime] = []
    available_kst_values: list[datetime] = []
    safe_dates: list[str] = []
    regimes: list[str] = []
    gap_policies: list[str] = []
    for observation_date in output["date"]:
        candidates = combined_dates[combined_dates > observation_date]
        if candidates.empty:
            raise RuntimeError(
                f"미국 금리 관측일 이후 확인된 H.15 공개일이 없습니다: {observation_date.date()}"
            )
        release_date = pd.Timestamp(candidates[0])
        if release_date <= WEEKLY_REGIME_END:
            # 전체 역사 게시 시각이 확인되지 않아 ET 공개일 종료를 보수적 상한으로 둔다.
            available_et = datetime(
                release_date.year,
                release_date.month,
                release_date.day,
                23,
                59,
                59,
                tzinfo=NEW_YORK,
            )
            regime = "pre-2016-10-11 official weekly release; conservative ET day end"
        else:
            available_et = datetime(
                release_date.year,
                release_date.month,
                release_date.day,
                16,
                15,
                tzinfo=NEW_YORK,
            )
            regime = "post-2016-10-11 official daily H.15 calendar at 16:15 ET"
        available_kst = available_et.astimezone(SEOUL)
        if TRANSITION_OBSERVATION_START <= observation_date <= TRANSITION_OBSERVATION_END:
            gap_policy = "deferred to first confirmed daily release on 2017-01-03"
        elif MISSING_MONTH_START <= observation_date <= MISSING_MONTH_END:
            gap_policy = "deferred to next confirmed release after missing 2019-09 calendar"
        else:
            gap_policy = "none"
        release_values.append(release_date)
        available_et_values.append(available_et)
        available_kst_values.append(available_kst)
        safe_dates.append((available_kst.date() + timedelta(days=1)).isoformat())
        regimes.append(regime)
        gap_policies.append(gap_policy)

    output["h15_release_date"] = release_values
    output["us_yield_available_at_et"] = available_et_values
    output["us_yield_available_at_kst"] = available_kst_values
    output["us_yield_safe_from_krw_date"] = safe_dates
    output["us_yield_release_regime"] = regimes
    output["us_yield_gap_policy"] = gap_policies
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전체 한미 3년물에 안전 사용일을 연결합니다.")
    parser.add_argument("--kr-input-path", type=Path, default=KR_INPUT_PATH)
    parser.add_argument("--us-input-path", type=Path, default=US_INPUT_PATH)
    parser.add_argument("--weekly-manifest-path", type=Path, default=WEEKLY_MANIFEST_PATH)
    parser.add_argument("--weekly-archive-path", type=Path, default=WEEKLY_ARCHIVE_PATH)
    parser.add_argument("--daily-manifest-path", type=Path, default=DAILY_MANIFEST_PATH)
    parser.add_argument("--daily-archive-path", type=Path, default=DAILY_ARCHIVE_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path in (
        args.kr_input_path,
        args.us_input_path,
        args.weekly_manifest_path,
        args.weekly_archive_path,
        args.daily_manifest_path,
        args.daily_archive_path,
    ):
        if not path.exists():
            raise FileNotFoundError(f"전체 공개시점 입력 파일이 없습니다: {path}")
    weekly_dates = load_weekly_release_dates(
        args.weekly_manifest_path, args.weekly_archive_path
    )
    daily_dates = load_daily_release_dates(args.daily_manifest_path, args.daily_archive_path)
    kr = assign_kr_yield_availability(
        pd.read_csv(
            args.kr_input_path,
            dtype={"stat_code": str, "item_code": str, "series_code": str},
        )
    )
    us = assign_us_yield_full_availability(
        pd.read_csv(args.us_input_path), weekly_dates, daily_dates
    )
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    kr_period = f"{kr['date'].min():%Y%m%d}_{kr['date'].max():%Y%m%d}"
    us_period = f"{us['date'].min():%Y%m%d}_{us['date'].max():%Y%m%d}"
    kr_output = (
        PROCESSED_DIR / "ecos" / f"kr_treasury_3y_availability_{kr_period}_{timestamp}.csv"
    )
    us_output = (
        PROCESSED_DIR / "fred" / f"us_treasury_3y_availability_{us_period}_{timestamp}.csv"
    )
    if kr_output.exists() or us_output.exists():
        raise FileExistsError("기존 전체 한미 3년물 공개시점 파일을 덮어쓰지 않습니다.")
    serialize_availability(kr).to_csv(kr_output, index=False)
    serialize_availability(us).to_csv(us_output, index=False)

    transition_rows = us["us_yield_gap_policy"].str.startswith("deferred to first").sum()
    missing_month_rows = us["us_yield_gap_policy"].str.contains("missing 2019-09").sum()
    print(f"주간판 공식 공개일 수: {len(weekly_dates)}")
    print(f"일별 공식 공개일 수: {len(daily_dates)}")
    print(f"한국 금리 행 수: {len(kr)}")
    print(f"미국 금리 행 수: {len(us)}")
    print(f"미국 빈 값 행 수: {int(us['us_treasury_3y_percent'].isna().sum())}")
    print(f"2016 전환 공백 보수적 지연 행 수: {int(transition_rows)}")
    print(f"2019-09 공식 달력 결손 보수적 지연 행 수: {int(missing_month_rows)}")
    print(f"한국 공개시점 처리본: {kr_output}")
    print(f"미국 공개시점 처리본: {us_output}")


if __name__ == "__main__":
    main()
