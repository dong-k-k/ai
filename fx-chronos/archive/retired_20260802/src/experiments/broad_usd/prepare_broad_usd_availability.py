from __future__ import annotations

import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
RELEASE_DATES_URL = "https://www.federalreserve.gov/releases/h10/releaseDates.json"
INPUT_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "fred"
    / "broad_usd_index_20240101_20240331_20260802T073658Z.csv"
)
RAW_DIR = PROJECT_DIR / "data" / "raw" / "fred"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed" / "fred"
NEW_YORK = ZoneInfo("America/New_York")
SEOUL = ZoneInfo("Asia/Seoul")
WEEKLY_RELEASE_REGIME_START = pd.Timestamp("2009-01-05")


def fetch_release_dates_json() -> bytes:
    request = Request(RELEASE_DATES_URL, headers={"User-Agent": "fx-chronos/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"H.10 공개일 HTTP 상태가 200이 아닙니다: {response.status}"
                )
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"H.10 공개일 HTTP 오류가 발생했습니다: status={exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("H.10 공개일 요청에 실패했습니다. 네트워크를 확인하세요.") from exc


def parse_release_dates(raw_bytes: bytes) -> pd.DatetimeIndex:
    """연준 JSON의 실제 H.10 공개일을 검증하고 정렬한다."""
    try:
        payload: list[dict[str, Any]] = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("H.10 공개일 JSON을 해석할 수 없습니다.") from exc

    values: list[str] = []
    for year in payload:
        year_value = str(year.get("yearValue", ""))
        for month in year.get("Months", []):
            month_value = str(month.get("MonthValue", ""))
            for date_value in month.get("Dates", []):
                text = str(date_value)
                if not text.startswith(year_value) or not text.startswith(month_value):
                    raise RuntimeError(f"H.10 공개일의 연도·월 구조가 일치하지 않습니다: {text}")
                values.append(text)
    dates = pd.DatetimeIndex(pd.to_datetime(values, format="%Y%m%d", errors="raise"))
    if dates.empty or dates.duplicated().any():
        raise RuntimeError("H.10 공개일이 비었거나 중복됐습니다.")
    return dates.sort_values()


def assign_release_availability(
    observations: pd.DataFrame,
    release_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """각 관측 주가 끝난 뒤의 첫 공식 공개일과 보수적 한국 사용일을 연결한다."""
    required = {"date", "broad_usd_index", "series_id", "unit", "frequency"}
    missing = required - set(observations.columns)
    if missing:
        raise RuntimeError(f"Broad Dollar 처리본에 필수 열이 없습니다: {sorted(missing)}")
    output = observations.copy()
    output["date"] = pd.to_datetime(output["date"], errors="raise")
    if output["date"].duplicated().any() or not output["date"].is_monotonic_increasing:
        raise RuntimeError("Broad Dollar 관측 날짜가 중복됐거나 오름차순이 아닙니다.")

    release_date_values: list[pd.Timestamp | pd.NaT] = []
    available_et_values: list[datetime | pd.NaT] = []
    available_kst_values: list[datetime | pd.NaT] = []
    safe_dates: list[str] = []
    regimes: list[str] = []
    for observation_date in output["date"]:
        if observation_date < WEEKLY_RELEASE_REGIME_START:
            release_date_values.append(pd.NaT)
            available_et_values.append(pd.NaT)
            available_kst_values.append(pd.NaT)
            safe_dates.append("")
            regimes.append("pre-2009 daily-update availability not implemented")
            continue
        week_end = observation_date + pd.Timedelta(days=6 - observation_date.weekday())
        candidates = release_dates[release_dates > week_end]
        if candidates.empty:
            raise RuntimeError(
                f"관측 주 이후 H.10 공식 공개일이 없습니다: {observation_date.date()}"
            )
        release_date = pd.Timestamp(candidates[0])
        available_et = datetime(
            release_date.year,
            release_date.month,
            release_date.day,
            16,
            15,
            tzinfo=NEW_YORK,
        )
        available_kst = available_et.astimezone(SEOUL)
        # ECOS 일별 관측 시각을 확정하지 못했으므로 한국 공개 당일에는 사용하지 않는다.
        safe_date = available_kst.date() + timedelta(days=1)
        release_date_values.append(release_date)
        available_et_values.append(available_et)
        available_kst_values.append(available_kst)
        safe_dates.append(safe_date.isoformat())
        regimes.append("weekly H.10 official release calendar")

    output["h10_release_date"] = release_date_values
    output["available_at_et"] = available_et_values
    output["available_at_kst"] = available_kst_values
    output["safe_from_krw_date"] = safe_dates
    output["release_regime"] = regimes
    output["availability_rule"] = (
        "first official H.10 release after observation week; "
        "usable from calendar day after KST release date"
    )
    return output


def serialize_availability(dataframe: pd.DataFrame) -> pd.DataFrame:
    """CSV에서도 공개 시각과 UTC offset이 사라지지 않도록 문자열로 고정한다."""
    output = dataframe.copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    output["h10_release_date"] = pd.to_datetime(output["h10_release_date"]).dt.strftime("%Y-%m-%d").fillna("")
    output["available_at_et"] = output["available_at_et"].map(
        lambda value: "" if pd.isna(value) else value.isoformat()
    )
    output["available_at_kst"] = output["available_at_kst"].map(
        lambda value: "" if pd.isna(value) else value.isoformat()
    )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Broad Dollar 관측에 H.10 공개시점을 연결합니다.")
    parser.add_argument("--input-path", type=Path, default=INPUT_PATH)
    parser.add_argument("--release-calendar-path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input_path
    if not input_path.exists():
        raise FileNotFoundError(f"Broad Dollar 처리본이 없습니다: {input_path}")
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    raw_path = RAW_DIR / f"h10_release_dates_{timestamp}.json"
    observations = pd.read_csv(input_path)
    parsed_input_dates = pd.to_datetime(observations["date"], errors="raise")
    period = f"{parsed_input_dates.min():%Y%m%d}_{parsed_input_dates.max():%Y%m%d}"
    output_path = PROCESSED_DIR / f"broad_usd_index_availability_{period}_{timestamp}.csv"

    if args.release_calendar_path is None:
        if raw_path.exists() or output_path.exists():
            raise FileExistsError(f"기존 H.10 공개시점 결과를 덮어쓰지 않습니다: {timestamp}")
        raw_bytes = fetch_release_dates_json()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw_bytes)
        release_source = raw_path
    else:
        if not args.release_calendar_path.exists():
            raise FileNotFoundError(
                f"H.10 공개일 스냅샷이 없습니다: {args.release_calendar_path}"
            )
        if output_path.exists():
            raise FileExistsError(f"기존 H.10 공개시점 결과를 덮어쓰지 않습니다: {output_path}")
        raw_bytes = args.release_calendar_path.read_bytes()
        release_source = args.release_calendar_path
    release_dates = parse_release_dates(raw_bytes)
    result = assign_release_availability(observations, release_dates)
    supported = result["date"] >= WEEKLY_RELEASE_REGIME_START
    safe_dates = pd.to_datetime(result.loc[supported, "safe_from_krw_date"])
    available_dates = (
        pd.to_datetime(result.loc[supported, "available_at_kst"], utc=True)
        .dt.tz_convert(SEOUL)
        .dt.tz_localize(None)
        .dt.normalize()
    )
    if not (safe_dates > available_dates).all():
        raise RuntimeError("보수적 한국 사용 가능일이 공개일보다 늦지 않은 행이 있습니다.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialize_availability(result).to_csv(output_path, index=False)

    print(f"공식 공개일 최초 연도: {release_dates.min().year}")
    print(f"공식 공개일 최종 연도: {release_dates.max().year}")
    print(f"공식 공개일 수: {len(release_dates)}")
    print(f"관측 행 수: {len(result)}")
    print(f"빈 지수값 행 수: {int(result['broad_usd_index'].isna().sum())}")
    print(f"공개시점 확인 필요 행 수: {int((~supported).sum())}")
    print(f"주간 공개시점 적용 행 수: {int(supported.sum())}")
    print(f"최초 관측일: {result['date'].min().date()}")
    print(f"최초 H.10 공개일: {result['h10_release_date'].min().date()}")
    print(f"최초 안전 사용일: {result.loc[supported, 'safe_from_krw_date'].min()}")
    print(f"공개일 스냅샷 경로: {release_source}")
    print(f"공개시점 처리본 저장 경로: {output_path}")


if __name__ == "__main__":
    main()
