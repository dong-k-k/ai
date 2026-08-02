from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw" / "fred"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
KR_INPUT_PATH = (
    PROCESSED_DIR / "ecos" / "kr_treasury_3y_20240701_20240710.csv"
)
US_INPUT_PATH = (
    PROCESSED_DIR
    / "fred"
    / "us_treasury_3y_20240701_20240710_20260802T115445Z.csv"
)
NEW_YORK = ZoneInfo("America/New_York")
SEOUL = ZoneInfo("Asia/Seoul")
MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
H15_CALENDAR_URL_OVERRIDES = {
    (2019, 7): "https://www.federalreserve.gov/newsevents/2019-07.htm",
    # 연준 페이지 URL에는 September가 들어가지만 실제 HTML 제목과 내용은 August다.
    (2019, 8): "https://www.federalreserve.gov/newsevents/2019-September.htm",
}


class ParagraphTextParser(HTMLParser):
    """Collect visible text from each paragraph without external HTML packages."""

    def __init__(self) -> None:
        super().__init__()
        self.paragraphs: list[str] = []
        self._inside_paragraph = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "p":
            self._inside_paragraph = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_paragraph:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "p" and self._inside_paragraph:
            text = " ".join("".join(self._parts).split())
            self.paragraphs.append(text)
            self._inside_paragraph = False
            self._parts = []


def build_h15_calendar_url(year: int, month: int) -> str:
    if year < 1900:
        raise ValueError("H.15 달력 연도는 1900 이상이어야 합니다.")
    if month < 1 or month > 12:
        raise ValueError("H.15 달력 월은 1~12여야 합니다.")
    override = H15_CALENDAR_URL_OVERRIDES.get((year, month))
    if override is not None:
        return override
    return f"https://www.federalreserve.gov/newsevents/{year}-{MONTH_NAMES[month - 1]}.htm"


def fetch_h15_calendar(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "fx-chronos/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"연준 달력 HTTP 상태가 200이 아닙니다: {response.status}")
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"연준 달력 HTTP 오류가 발생했습니다: status={exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("연준 달력 요청에 실패했습니다. 네트워크를 확인하세요.") from exc


def parse_h15_release_dates(raw_bytes: bytes, year: int, month: int) -> pd.DatetimeIndex:
    """Parse the official H.15 release dates and verify the stated release time."""
    try:
        html = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("연준 달력 HTML을 UTF-8로 해석할 수 없습니다.") from exc
    expected_title = f"Calendar: {MONTH_NAMES[month - 1].title()} {year}"
    if expected_title not in html:
        raise RuntimeError(f"연준 달력 HTML의 실제 연월이 예상과 다릅니다: {expected_title}")
    parser = ParagraphTextParser()
    parser.feed(html)
    nonempty = [text for text in parser.paragraphs if text]
    label = "H.15 - Selected Interest Rates"
    matches = [index for index, text in enumerate(nonempty) if text == label]
    if len(matches) != 1:
        raise RuntimeError(f"연준 달력에서 H.15 행을 하나로 식별하지 못했습니다: {len(matches)}건")
    index = matches[0]
    if index == 0 or index + 1 >= len(nonempty):
        raise RuntimeError("연준 달력 H.15 행의 시간 또는 날짜가 없습니다.")
    if nonempty[index - 1] != "4:15 p.m.":
        raise RuntimeError(f"H.15 공개 시각이 예상과 다릅니다: {nonempty[index - 1]}")

    day_tokens = [token.strip() for token in nonempty[index + 1].split(",")]
    try:
        days = [int(token) for token in day_tokens]
        dates = pd.DatetimeIndex(
            pd.to_datetime([f"{year:04d}-{month:02d}-{day:02d}" for day in days])
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"H.15 공개일 목록을 해석할 수 없습니다: {day_tokens}") from exc
    if dates.empty or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise RuntimeError("H.15 공개일이 비었거나 중복됐거나 오름차순이 아닙니다.")
    if not ((dates.year == year) & (dates.month == month)).all():
        raise RuntimeError("H.15 공개일이 요청한 연월을 벗어났습니다.")
    return dates


def assign_kr_yield_availability(observations: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "value", "stat_code", "item_code", "item_name", "unit_name"}
    missing = required - set(observations.columns)
    if missing:
        raise RuntimeError(f"한국 3년물 처리본에 필수 열이 없습니다: {sorted(missing)}")
    output = observations.copy()
    output["date"] = pd.to_datetime(output["date"], errors="raise")
    if output["date"].duplicated().any() or not output["date"].is_monotonic_increasing:
        raise RuntimeError("한국 3년물 날짜가 중복됐거나 오름차순이 아닙니다.")
    if set(output["stat_code"].astype(str)) != {"817Y002"}:
        raise RuntimeError("한국 3년물 통계표 코드가 817Y002와 다릅니다.")
    if set(output["item_code"].astype(str).str.zfill(9)) != {"010200000"}:
        raise RuntimeError("한국 3년물 항목 코드가 010200000과 다릅니다.")
    # CSV 재로딩 시 선행 0이 사라져도 검증 후 공식 문자열 형식으로 복원한다.
    output["item_code"] = output["item_code"].astype(str).str.zfill(9)
    if set(output["item_name"].astype(str)) != {"국고채(3년)"}:
        raise RuntimeError("한국 3년물 항목명이 예상과 다릅니다.")
    if set(output["unit_name"].astype(str)) != {"연%"}:
        raise RuntimeError("한국 3년물 단위가 연%와 다릅니다.")

    available = output["date"].map(
        lambda date: datetime(date.year, date.month, date.day, 16, 0, tzinfo=SEOUL)
    )
    output["kr_yield_source_published_at_kst"] = available
    output["kr_yield_safe_from_krw_date"] = available.map(
        lambda value: (value.date() + timedelta(days=1)).isoformat()
    )
    output["kr_yield_availability_rule"] = (
        "KOFIA 16:00 KST source publication; usable from next calendar day; "
        "ECOS load time unverified"
    )
    return output


def assign_us_yield_availability(
    observations: pd.DataFrame,
    release_dates: pd.DatetimeIndex,
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

    release_values: list[pd.Timestamp] = []
    available_et_values: list[datetime] = []
    available_kst_values: list[datetime] = []
    safe_dates: list[str] = []
    for observation_date in output["date"]:
        candidates = release_dates[release_dates > observation_date]
        if candidates.empty:
            raise RuntimeError(
                f"미국 금리 관측일 이후 H.15 공식 공개일이 없습니다: {observation_date.date()}"
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
        release_values.append(release_date)
        available_et_values.append(available_et)
        available_kst_values.append(available_kst)
        safe_dates.append((available_kst.date() + timedelta(days=1)).isoformat())

    output["h15_release_date"] = release_values
    output["us_yield_available_at_et"] = available_et_values
    output["us_yield_available_at_kst"] = available_kst_values
    output["us_yield_safe_from_krw_date"] = safe_dates
    output["us_yield_availability_rule"] = (
        "first official H.15 release after observation date at 16:15 ET; "
        "usable from calendar day after KST release date"
    )
    return output


def serialize_availability(dataframe: pd.DataFrame) -> pd.DataFrame:
    output = dataframe.copy()
    output["date"] = pd.to_datetime(output["date"]).dt.strftime("%Y-%m-%d")
    for column in ("h15_release_date",):
        if column in output:
            output[column] = pd.to_datetime(output[column]).dt.strftime("%Y-%m-%d")
    for column in (
        "kr_yield_source_published_at_kst",
        "us_yield_available_at_et",
        "us_yield_available_at_kst",
    ):
        if column in output:
            output[column] = output[column].map(lambda value: value.isoformat())
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="한미 3년물에 공개시점 안전 사용일을 연결합니다.")
    parser.add_argument("--kr-input-path", type=Path, default=KR_INPUT_PATH)
    parser.add_argument("--us-input-path", type=Path, default=US_INPUT_PATH)
    parser.add_argument("--calendar-year", type=int, default=2024)
    parser.add_argument("--calendar-month", type=int, default=7)
    parser.add_argument("--calendar-path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path in (args.kr_input_path, args.us_input_path):
        if not path.exists():
            raise FileNotFoundError(f"금리 처리본이 없습니다: {path}")
    collected_at = datetime.now(timezone.utc)
    timestamp = collected_at.strftime("%Y%m%dT%H%M%SZ")
    calendar_url = build_h15_calendar_url(args.calendar_year, args.calendar_month)
    raw_path = RAW_DIR / f"h15_calendar_{args.calendar_year}{args.calendar_month:02d}_{timestamp}.html"

    if args.calendar_path is None:
        raw_bytes = fetch_h15_calendar(calendar_url)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        if raw_path.exists():
            raise FileExistsError(f"기존 H.15 달력 원본을 덮어쓰지 않습니다: {raw_path}")
        raw_path.write_bytes(raw_bytes)
        calendar_source = raw_path
    else:
        if not args.calendar_path.exists():
            raise FileNotFoundError(f"H.15 달력 스냅샷이 없습니다: {args.calendar_path}")
        raw_bytes = args.calendar_path.read_bytes()
        calendar_source = args.calendar_path

    release_dates = parse_h15_release_dates(
        raw_bytes, args.calendar_year, args.calendar_month
    )
    kr = assign_kr_yield_availability(
        pd.read_csv(
            args.kr_input_path,
            dtype={"stat_code": str, "item_code": str, "series_code": str},
        )
    )
    us = assign_us_yield_availability(pd.read_csv(args.us_input_path), release_dates)
    kr_period = f"{kr['date'].min():%Y%m%d}_{kr['date'].max():%Y%m%d}"
    us_period = f"{us['date'].min():%Y%m%d}_{us['date'].max():%Y%m%d}"
    kr_output = PROCESSED_DIR / "ecos" / f"kr_treasury_3y_availability_{kr_period}_{timestamp}.csv"
    us_output = PROCESSED_DIR / "fred" / f"us_treasury_3y_availability_{us_period}_{timestamp}.csv"
    if kr_output.exists() or us_output.exists():
        raise FileExistsError("기존 한미 3년물 공개시점 결과를 덮어쓰지 않습니다.")
    kr_output.parent.mkdir(parents=True, exist_ok=True)
    us_output.parent.mkdir(parents=True, exist_ok=True)
    serialize_availability(kr).to_csv(kr_output, index=False)
    serialize_availability(us).to_csv(us_output, index=False)

    print(f"H.15 공식 달력 URL: {calendar_url}")
    print(f"H.15 공식 공개일 수: {len(release_dates)}")
    print(f"H.15 공식 공개일: {', '.join(release_dates.strftime('%Y-%m-%d'))}")
    print(f"한국 금리 행 수: {len(kr)}")
    print(f"미국 금리 행 수: {len(us)}")
    print(f"미국 빈 값 행 수: {int(us['us_treasury_3y_percent'].isna().sum())}")
    print(f"H.15 달력 원본: {calendar_source}")
    print(f"한국 공개시점 처리본: {kr_output}")
    print(f"미국 공개시점 처리본: {us_output}")


if __name__ == "__main__":
    main()
