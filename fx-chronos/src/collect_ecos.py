from __future__ import annotations

import csv
import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "ecos"
PROCESSED_DIR = DATA_DIR / "processed"
ECOS_PROCESSED_DIR = PROCESSED_DIR / "ecos"
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
ECOS_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_dotenv() -> None:
    """Load environment variables from a nearby .env file if present."""
    search_roots = (
        Path.cwd(),
        Path(__file__).resolve().parent,
        Path(__file__).resolve().parent.parent,
        Path(__file__).resolve().parent.parent.parent,
    )

    for root in search_roots:
        env_path = root / ".env"
        if not env_path.exists():
            continue

        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        break


def get_api_key() -> str:
    """Read the ECOS API key from the environment or .env file."""
    load_dotenv()
    api_key = os.getenv("ECOS_API_KEY")
    if not api_key:
        raise RuntimeError("ECOS_API_KEY 환경변수가 설정되지 않았습니다.")
    return api_key


def request_ecos(service: str, path_parts: list[str]) -> dict[str, Any]:
    """Send a request to an ECOS Open API service and return the parsed JSON payload."""
    api_key = get_api_key()
    base_url = f"https://ecos.bok.or.kr/api/{service}/{api_key}/json/kr"
    masked_base_url = f"https://ecos.bok.or.kr/api/{service}/***/json/kr"
    endpoint = "/".join(path_parts)
    url = f"{base_url}/{endpoint}" if endpoint else base_url
    masked_url = f"{masked_base_url}/{endpoint}" if endpoint else masked_base_url

    print(f"ECOS request URL: {masked_url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            payload = json.load(response)
    except Exception as exc:
        # urllib 예외에는 인증키가 포함된 실제 URL이 들어갈 수 있으므로 원문을 출력하지 않는다.
        raise RuntimeError(f"ECOS API 호출 실패: {service} ({type(exc).__name__})") from None

    result = payload.get("RESULT", {})
    code = result.get("CODE")
    if code and code != "INFO-000":
        raise RuntimeError(f"ECOS API 오류: {service} -> {result.get('MESSAGE', 'unknown error')}")
    return payload


def extract_rows(payload: dict[str, Any], service: str) -> list[dict[str, Any]]:
    container = payload.get(service, {})
    return container.get("row", []) if isinstance(container, dict) else []


def fetch_all_pages(service: str, path_parts: list[str], page_size: int = 100) -> list[dict[str, Any]]:
    """Fetch all available pages for ECOS list services."""
    rows: list[dict[str, Any]] = []
    start_index = 1
    end_index = page_size
    total_count = None

    while True:
        if service == "StatisticItemList":
            current_path = [str(start_index), str(end_index), path_parts[0]] if path_parts else [str(start_index), str(end_index)]
        else:
            current_path = [str(start_index), str(end_index)]
        payload = request_ecos(service, current_path)
        page_rows = extract_rows(payload, service)
        if not page_rows:
            break

        rows.extend(page_rows)

        if total_count is None:
            container = payload.get(service, {})
            total_count = container.get("list_total_count")
            if total_count is None:
                total_count = len(page_rows)

        if len(page_rows) < page_size:
            break
        if total_count is not None and len(rows) >= int(total_count):
            break

        start_index += page_size
        end_index += page_size

    return rows


def search_statistic_tables(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only likely currency-related tables and rank them by relevance."""
    keywords = ["환율", "대원화", "미국달러", "주요국 통화", "원/미국달러"]
    matched: list[dict[str, Any]] = []
    for row in rows:
        stat_name = str(row.get("STAT_NAME", ""))
        if any(keyword in stat_name for keyword in keywords):
            cycle = str(row.get("CYCLE", ""))
            priority_score = 0
            if cycle == "D":
                priority_score += 100
            if "대원화환율" in stat_name:
                priority_score += 50
            if "대원화" in stat_name:
                priority_score += 20
            if "주요국 통화" in stat_name:
                priority_score += 15
            if "미국달러" in stat_name:
                priority_score += 10
            if "환율" in stat_name:
                priority_score += 5

            matched.append(
                {
                    "STAT_CODE": row.get("STAT_CODE"),
                    "STAT_NAME": row.get("STAT_NAME"),
                    "CYCLE": row.get("CYCLE"),
                    "SRCH_YN": row.get("SRCH_YN"),
                    "ORG_NAME": row.get("ORG_NAME"),
                    "priority_score": priority_score,
                }
            )

    matched.sort(key=lambda item: (-item["priority_score"], str(item["STAT_NAME"])))
    return matched


def get_item_code_value(row: dict[str, Any]) -> str | None:
    for key in ["ITEM_CODE", "ITEM_CODE1", "ITEM_CODE2", "ITEM_CODE3", "ITEM_CODE4"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def get_item_name_value(row: dict[str, Any]) -> str | None:
    for key in ["ITEM_NAME", "ITEM_NAME1", "ITEM_NAME2", "ITEM_NAME3", "ITEM_NAME4"]:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def search_usdkrw_items(rows: list[dict[str, Any]], stat_code: str) -> list[dict[str, Any]]:
    """Search for USD/KRW-like item names within a statistic table."""
    matched: list[dict[str, Any]] = []
    for row in rows:
        item_name = get_item_name_value(row) or ""
        item_code = get_item_code_value(row)
        text = item_name.lower()
        if any(term in text for term in ["미국달러", "원/미국달러", "달러", "usd", "매매기준율"]):
            score = 0
            if "원/미국달러" in item_name:
                score += 5
            if "미국달러" in item_name:
                score += 3
            if "매매기준율" in item_name:
                score += 2
            if "usd" in text:
                score += 2
            matched.append(
                {
                    "STAT_CODE": stat_code,
                    "STAT_NAME": row.get("STAT_NAME"),
                    "ITEM_CODE": item_code,
                    "ITEM_NAME": item_name,
                    "ITEM_CODE1": row.get("ITEM_CODE1"),
                    "ITEM_NAME1": row.get("ITEM_NAME1"),
                    "ITEM_CODE2": row.get("ITEM_CODE2"),
                    "ITEM_NAME2": row.get("ITEM_NAME2"),
                    "ITEM_CODE3": row.get("ITEM_CODE3"),
                    "ITEM_NAME3": row.get("ITEM_NAME3"),
                    "ITEM_CODE4": row.get("ITEM_CODE4"),
                    "ITEM_NAME4": row.get("ITEM_NAME4"),
                    "CYCLE": row.get("CYCLE"),
                    "UNIT_NAME": row.get("UNIT_NAME"),
                    "START_TIME": row.get("START_TIME"),
                    "END_TIME": row.get("END_TIME"),
                    "DATA_CNT": row.get("DATA_CNT"),
                    "score": score,
                }
            )

    matched.sort(key=lambda item: (-item["score"], str(item["ITEM_NAME"])))
    return matched


def fetch_statistic_items(stat_code: str) -> list[dict[str, Any]]:
    """Fetch all items for a given ECOS statistic table."""
    return fetch_all_pages("StatisticItemList", [stat_code])


def verify_series(stat_code: str, item_code: str) -> dict[str, Any]:
    """Verify that a stat code and item code combination can return sample rows."""
    now = datetime.now()
    end_date = now.strftime("%Y%m%d")
    start_date = (now - timedelta(days=90)).strftime("%Y%m%d")
    payload = request_ecos("StatisticSearch", ["1", "100", stat_code, "D", start_date, end_date])
    rows = extract_rows(payload, "StatisticSearch")
    filtered = [row for row in rows if str(row.get("ITEM_CODE1", row.get("ITEM_CODE", ""))) == item_code]

    if not filtered:
        fallback_end = (now - timedelta(days=90)).strftime("%Y%m%d")
        fallback_start = (now - timedelta(days=180)).strftime("%Y%m%d")
        payload = request_ecos("StatisticSearch", ["1", "100", stat_code, "D", fallback_start, fallback_end])
        rows = extract_rows(payload, "StatisticSearch")
        filtered = [row for row in rows if str(row.get("ITEM_CODE1", row.get("ITEM_CODE", ""))) == item_code]

    sample = filtered[0] if filtered else None
    return {
        "success": bool(sample),
        "sample_time": sample.get("TIME") if sample else None,
        "sample_value": sample.get("DATA_VALUE") if sample else None,
        "stat_code": stat_code,
        "item_code": item_code,
        "stat_name": sample.get("STAT_NAME") if sample else None,
        "item_name": sample.get("ITEM_NAME1") if sample else None,
    }


def save_json(payload: dict[str, Any], out_path: Path) -> None:
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def save_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    if not rows:
        out_path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_results(
    table_candidates: list[dict[str, Any]],
    item_candidates: list[dict[str, Any]],
    metadata: dict[str, Any],
    selection_rows: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> None:
    save_csv(table_candidates, ECOS_PROCESSED_DIR / "usdkrw_table_candidates.csv")
    save_csv(item_candidates, ECOS_PROCESSED_DIR / "usdkrw_item_candidates.csv")
    save_csv(selection_rows, ECOS_PROCESSED_DIR / "usdkrw_candidate_selection.csv")
    save_csv(failures, ECOS_PROCESSED_DIR / "usdkrw_candidate_failures.csv")
    save_json(metadata, ECOS_PROCESSED_DIR / "usdkrw_metadata.json")

    table_raw_path = RAW_DIR / "statistic_tables.json"
    sample_raw_path = RAW_DIR / "usdkrw_sample.json"
    failure_raw_path = RAW_DIR / "usdkrw_candidate_failures.json"

    save_json({"rows": table_candidates}, table_raw_path)
    save_json(metadata, sample_raw_path)
    save_json({"rows": failures}, failure_raw_path)


def fetch_ecos_series(
    stat_code: str,
    item_code: str,
    start_date: str,
    end_date: str,
    cycle: str = "D",
    page_size: int = 1000,
) -> dict[str, Any]:
    """Fetch every page for one explicitly selected ECOS series."""
    all_rows: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    start_index = 1
    total_count: int | None = None

    while total_count is None or len(all_rows) < total_count:
        end_index = start_index + page_size - 1
        path_parts = [
            str(start_index),
            str(end_index),
            stat_code,
            cycle,
            start_date,
            end_date,
            item_code,
        ]
        payload = request_ecos("StatisticSearch", path_parts)
        container = payload.get("StatisticSearch", {})
        if not isinstance(container, dict):
            raise RuntimeError("StatisticSearch 응답 형식이 올바르지 않습니다.")

        page_rows = container.get("row", [])
        if not isinstance(page_rows, list):
            raise RuntimeError("StatisticSearch.row가 목록 형식이 아닙니다.")

        if total_count is None:
            raw_total_count = container.get("list_total_count")
            if raw_total_count is None:
                raise RuntimeError("StatisticSearch.list_total_count가 없습니다.")
            total_count = int(raw_total_count)

        pages.append(
            {
                "start_index": start_index,
                "end_index": end_index,
                "row_count": len(page_rows),
            }
        )
        if not page_rows:
            break

        all_rows.extend(page_rows)
        start_index += page_size

    return {
        "service": "StatisticSearch",
        "query": {
            "stat_code": stat_code,
            "cycle": cycle,
            "start_date": start_date,
            "end_date": end_date,
            "item_code": item_code,
            "page_size": page_size,
        },
        "list_total_count": total_count or 0,
        "pages": pages,
        "rows": all_rows,
    }


def extract_rows_for_series(payload: dict[str, Any], item_code: str) -> list[dict[str, Any]]:
    rows = payload.get("rows", [])
    if not rows:
        rows = extract_rows(payload, "StatisticSearch")
    if not rows:
        raise RuntimeError("No rows returned from ECOS API")

    filtered = [row for row in rows if str(row.get("ITEM_CODE1", row.get("ITEM_CODE", ""))) == item_code]
    if not filtered:
        raise RuntimeError(f"Item code {item_code} was not found in the ECOS response")
    return filtered


def convert_value(raw_value: str, item_name: str) -> float:
    value = float(raw_value)
    if "100엔" in item_name:
        return value / 100.0
    return value


def save_records(records: list[dict[str, Any]], out_path: Path) -> None:
    fieldnames = ["date", "value", "item_code", "item_name", "unit_name", "series_code", "notes"]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def validate_date(date_value: str, field_name: str) -> None:
    """Validate an ECOS daily date argument without changing its value."""
    try:
        datetime.strptime(date_value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"{field_name}는 YYYYMMDD 형식이어야 합니다: {date_value}") from exc


def collect_series(
    stat_code: str,
    item_code: str,
    output_name: str,
    description: str,
    start_date: str,
    end_date: str,
    cycle: str = "D",
    expected_item_name: str = "원/미국달러(매매기준율)",
) -> Path:
    validate_date(start_date, "start_date")
    validate_date(end_date, "end_date")
    if start_date > end_date:
        raise ValueError("start_date는 end_date보다 늦을 수 없습니다.")

    payload = fetch_ecos_series(stat_code, item_code, start_date, end_date, cycle=cycle)
    rows = payload["rows"]

    records: list[dict[str, Any]] = []
    invalid_stat_code = 0
    invalid_item_code = 0
    invalid_item_name = 0
    mixed_item_count = 0
    missing_time = 0
    blank_data_value = 0
    numeric_conversion_failures = 0
    out_of_range = 0

    for row in rows:
        if str(row.get("STAT_CODE", "")) != stat_code:
            invalid_stat_code += 1
        item_code_mismatch = str(row.get("ITEM_CODE1", "")) != item_code
        item_name_mismatch = str(row.get("ITEM_NAME1", "")) != expected_item_name
        if item_code_mismatch:
            invalid_item_code += 1
        if item_name_mismatch:
            invalid_item_name += 1
        if item_code_mismatch or item_name_mismatch:
            mixed_item_count += 1

        raw_date = str(row.get("TIME", ""))
        if not raw_date:
            missing_time += 1
        elif raw_date < start_date or raw_date > end_date:
            out_of_range += 1

        raw_value = row.get("DATA_VALUE")
        if raw_value in (None, ""):
            blank_data_value += 1
            continue
        try:
            value = float(str(raw_value))
        except (TypeError, ValueError):
            numeric_conversion_failures += 1
            continue

        if len(raw_date) == 8:
            iso_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        else:
            iso_date = raw_date

        item_name = str(row.get("ITEM_NAME1", row.get("ITEM_NAME", "")))
        records.append(
            {
                "date": iso_date,
                "value": value,
                "stat_code": stat_code,
                "item_code": item_code,
                "item_name": item_name,
                "unit_name": row.get("UNIT_NAME", ""),
                "series_code": stat_code,
                "notes": description,
            }
        )

    validation_errors = (
        invalid_stat_code
        + invalid_item_code
        + invalid_item_name
        + missing_time
        + blank_data_value
        + numeric_conversion_failures
        + out_of_range
    )
    if validation_errors:
        raise RuntimeError(
            "ECOS 응답 검증 실패: "
            f"통계표 코드 오류={invalid_stat_code}, USD 외 항목 혼입={mixed_item_count}, "
            f"TIME 누락={missing_time}, 빈 DATA_VALUE={blank_data_value}, "
            f"숫자 변환 실패={numeric_conversion_failures}, 기간 밖 데이터={out_of_range}"
        )

    records.sort(key=lambda record: record["date"])
    dates = [record["date"] for record in records]
    duplicate_date_count = len(dates) - len(set(dates))
    if duplicate_date_count:
        raise RuntimeError(f"중복 날짜가 발견되었습니다: {duplicate_date_count}건")

    total_count = int(payload["list_total_count"])
    if len(rows) != total_count:
        raise RuntimeError(
            f"ECOS list_total_count와 실제 수집 행 수가 다릅니다: "
            f"list_total_count={total_count}, 실제={len(rows)}"
        )

    requested_dates = {
        date.strftime("%Y-%m-%d")
        for date in (
            datetime.strptime(start_date, "%Y%m%d") + timedelta(days=offset)
            for offset in range(
                (datetime.strptime(end_date, "%Y%m%d") - datetime.strptime(start_date, "%Y%m%d")).days + 1
            )
        )
    }
    missing_calendar_dates = sorted(requested_dates - set(dates))
    collected_at = datetime.now().strftime("%Y%m%dT%H%M%S")
    raw_out_path = RAW_DIR / f"usdkrw_{start_date}_{end_date}_{collected_at}.json"
    out_path = ECOS_PROCESSED_DIR / f"usdkrw_{start_date}_{end_date}.csv"
    if raw_out_path.exists() or out_path.exists():
        raise FileExistsError(f"기존 결과 파일을 덮어쓰지 않습니다: {raw_out_path} 또는 {out_path}")

    quality_summary = {
        "requested_period": f"{start_date}~{end_date}",
        "list_total_count": total_count,
        "collected_row_count": len(rows),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "duplicate_date_count": duplicate_date_count,
        "blank_data_value_count": blank_data_value,
        "numeric_conversion_failure_count": numeric_conversion_failures,
        "non_usd_item_count": mixed_item_count,
        "missing_calendar_dates": missing_calendar_dates,
    }
    payload["quality_summary"] = quality_summary
    payload["collected_at"] = collected_at

    save_json(payload, raw_out_path)
    save_csv(records, out_path)

    print(f"Saved {description} to {out_path}")
    print(f"Saved raw payload to {raw_out_path}")
    print(f"요청 기간: {quality_summary['requested_period']}")
    print(f"ECOS list_total_count: {total_count}")
    print(f"실제 수집 행 수: {len(rows)}")
    print(f"최초 날짜: {quality_summary['first_date']}")
    print(f"최종 날짜: {quality_summary['last_date']}")
    print(f"중복 날짜 수: {duplicate_date_count}")
    print(f"빈 DATA_VALUE 수: {blank_data_value}")
    print(f"숫자 변환 실패 수: {numeric_conversion_failures}")
    print(f"USD 외 항목 혼입 수: {mixed_item_count}")
    print(f"저장 경로: {out_path}")
    return out_path


def main() -> None:
    print("[ECOS USD/KRW 메타데이터 조회 결과]")

    table_rows = fetch_all_pages("StatisticTableList", [])
    table_candidates = search_statistic_tables(table_rows)
    if not table_candidates:
        raise RuntimeError("No matching statistic tables were found in the ECOS response")

    print(f"Selected statistic table candidates: {len(table_candidates)}")

    selected_table: dict[str, Any] | None = None
    selected_items: list[dict[str, Any]] = []
    selected_item_code = ""
    selected_item_name = ""
    verification: dict[str, Any] | None = None
    failures: list[dict[str, str]] = []
    selection_rows: list[dict[str, Any]] = []

    for table in table_candidates:
        stat_code = str(table.get("STAT_CODE", ""))
        if not stat_code:
            continue

        try:
            item_rows = fetch_statistic_items(stat_code)
        except RuntimeError as exc:
            failures.append({"stat_code": stat_code, "reason": str(exc)})
            selection_rows.append(
                {
                    "STAT_CODE": stat_code,
                    "STAT_NAME": table.get("STAT_NAME"),
                    "CYCLE": table.get("CYCLE"),
                    "ITEM_CODE": "",
                    "ITEM_NAME": "",
                    "SELECTION": "NO",
                    "JUDGMENT_REASON": str(exc),
                }
            )
            continue

        item_candidates = search_usdkrw_items(item_rows, stat_code)
        if not item_candidates:
            failures.append({"stat_code": stat_code, "reason": "No USD/KRW-like item candidates"})
            selection_rows.append(
                {
                    "STAT_CODE": stat_code,
                    "STAT_NAME": table.get("STAT_NAME"),
                    "CYCLE": table.get("CYCLE"),
                    "ITEM_CODE": "",
                    "ITEM_NAME": "",
                    "SELECTION": "NO",
                    "JUDGMENT_REASON": "No USD/KRW-like item candidates",
                }
            )
            continue

        raw_item_path = RAW_DIR / f"statistic_items_{stat_code}.json"
        save_json({"rows": item_rows}, raw_item_path)

        selected_table = table
        selected_items = item_candidates
        best_item = item_candidates[0]
        selected_item_code = str(best_item["ITEM_CODE"])
        selected_item_name = str(best_item["ITEM_NAME"])
        verification = verify_series(stat_code, selected_item_code)
        selection_rows.append(
            {
                "STAT_CODE": stat_code,
                "STAT_NAME": table.get("STAT_NAME"),
                "CYCLE": table.get("CYCLE"),
                "ITEM_CODE": selected_item_code,
                "ITEM_NAME": selected_item_name,
                "SELECTION": "YES",
                "JUDGMENT_REASON": "Matched USD/KRW-like item and verified with StatisticSearch",
            }
        )
        break

    if not selected_table or not verification:
        raise RuntimeError(f"No usable USD/KRW table and item candidates were found. Failures: {failures}")

    metadata = {
        "stat_code": str(selected_table.get("STAT_CODE", "")),
        "stat_name": str(selected_table.get("STAT_NAME", "")),
        "cycle": selected_table.get("CYCLE"),
        "item_code": selected_item_code,
        "item_name": selected_item_name,
        "verification": verification,
        "source": "Bank of Korea ECOS Open API",
    }

    save_results(table_candidates, selected_items, metadata, selection_rows, failures)

    print("1. 통계표")
    print(f"- 통계표명: {metadata['stat_name']}")
    print(f"- 통계표 코드: {metadata['stat_code']}")
    print(f"- 주기: {metadata['cycle']}")

    print("\n2. 세부 항목")
    print(f"- 항목명: {metadata['item_name']}")
    print(f"- 항목 코드: {metadata['item_code']}")

    print("\n3. 실제 조회 검증")
    print(f"- 검증 성공 여부: {metadata['verification']['success']}")
    print(f"- 샘플 기준 시점: {metadata['verification']['sample_time']}")
    print(f"- 샘플 데이터 존재 여부: {metadata['verification']['sample_value'] is not None}")

    print("\n4. 근거")
    print(f"- 선택된 통계표 후보 수: {len(table_candidates)}")
    print(f"- 선택된 항목 후보 수: {len(selected_items)}")
    print(f"- 후보 탐색 실패 수: {len(failures)}")

    print("\n5. 저장 파일")
    print(f"- {ECOS_PROCESSED_DIR / 'usdkrw_table_candidates.csv'}")
    print(f"- {ECOS_PROCESSED_DIR / 'usdkrw_item_candidates.csv'}")
    print(f"- {ECOS_PROCESSED_DIR / 'usdkrw_metadata.json'}")

    collect_series(
        str(selected_table.get("STAT_CODE", "")),
        selected_item_code,
        "usd_krw_krw_per_usd.csv",
        "USD/KRW (KRW per USD)",
        start_date="20240101",
        end_date="20240331",
    )


if __name__ == "__main__":
    main()
