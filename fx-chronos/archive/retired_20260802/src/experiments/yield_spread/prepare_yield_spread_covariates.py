from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.experiments.jpy.prepare_covariates import validate_weekday_series


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
USD_PATH = PROCESSED_DIR / "usd_krw_model_weekdays_19640504_20260730.csv"
KR_PATH = (
    PROCESSED_DIR
    / "ecos"
    / "kr_treasury_3y_availability_20141209_20211231_20260802T123348Z.csv"
)
US_PATH = (
    PROCESSED_DIR
    / "fred"
    / "us_treasury_3y_availability_20141209_20211231_20260802T123348Z.csv"
)


def validate_kr_yield(dataframe: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "normalized_rate",
        "normalized_unit",
        "stat_code",
        "item_code",
        "item_name",
        "kr_yield_source_published_at_kst",
        "kr_yield_safe_from_krw_date",
        "kr_yield_availability_rule",
    }
    missing = required - set(dataframe.columns)
    if missing:
        raise RuntimeError(f"한국 3년물 공개시점 데이터에 필수 열이 없습니다: {sorted(missing)}")
    output = dataframe[list(required)].copy().rename(
        columns={
            "date": "kr_yield_observation_date",
            "normalized_rate": "kr_treasury_3y_percent",
        }
    )
    output["kr_yield_observation_date"] = pd.to_datetime(
        output["kr_yield_observation_date"], errors="coerce"
    )
    output["kr_yield_safe_from_krw_date"] = pd.to_datetime(
        output["kr_yield_safe_from_krw_date"], errors="coerce"
    )
    output["kr_treasury_3y_percent"] = pd.to_numeric(
        output["kr_treasury_3y_percent"], errors="coerce"
    )
    if output["kr_yield_observation_date"].isna().any():
        raise RuntimeError("한국 3년물에 변환할 수 없는 관측 날짜가 있습니다.")
    if output["kr_yield_observation_date"].duplicated().any():
        raise RuntimeError("한국 3년물에 중복 관측 날짜가 있습니다.")
    if set(output["stat_code"].astype(str)) != {"817Y002"}:
        raise RuntimeError("한국 3년물 통계표 코드가 817Y002와 다릅니다.")
    if set(output["item_code"].astype(str)) != {"010200000"}:
        raise RuntimeError("한국 3년물 항목 코드가 010200000과 다릅니다.")
    if set(output["normalized_unit"].astype(str)) != {"연%"}:
        raise RuntimeError("한국 3년물 단위가 연%와 다릅니다.")
    return output.sort_values("kr_yield_observation_date").reset_index(drop=True)


def validate_us_yield(dataframe: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "us_treasury_3y_percent",
        "series_id",
        "unit",
        "frequency",
        "h15_release_date",
        "us_yield_available_at_et",
        "us_yield_available_at_kst",
        "us_yield_safe_from_krw_date",
        "us_yield_release_regime",
        "us_yield_gap_policy",
    }
    missing = required - set(dataframe.columns)
    if missing:
        raise RuntimeError(f"미국 3년물 공개시점 데이터에 필수 열이 없습니다: {sorted(missing)}")
    output = dataframe[list(required)].copy().rename(
        columns={"date": "us_yield_observation_date"}
    )
    output["us_yield_observation_date"] = pd.to_datetime(
        output["us_yield_observation_date"], errors="coerce"
    )
    output["us_yield_safe_from_krw_date"] = pd.to_datetime(
        output["us_yield_safe_from_krw_date"], errors="coerce"
    )
    output["us_treasury_3y_percent"] = pd.to_numeric(
        output["us_treasury_3y_percent"], errors="coerce"
    )
    if output["us_yield_observation_date"].isna().any():
        raise RuntimeError("미국 3년물에 변환할 수 없는 관측 날짜가 있습니다.")
    if output["us_yield_observation_date"].duplicated().any():
        raise RuntimeError("미국 3년물에 중복 관측 날짜가 있습니다.")
    if set(output["series_id"].astype(str)) != {"DGS3"}:
        raise RuntimeError("미국 3년물 series ID가 DGS3와 다릅니다.")
    if set(output["unit"].astype(str)) != {"Percent"}:
        raise RuntimeError("미국 3년물 단위가 Percent와 다릅니다.")
    return output.sort_values("us_yield_observation_date").reset_index(drop=True)


def latest_available_states(
    dataframe: pd.DataFrame,
    observation_column: str,
    safe_column: str,
    value_column: str,
    source: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invalid_safe = dataframe[safe_column].isna()
    empty_value = dataframe[value_column].isna()
    audit = dataframe.loc[invalid_safe | empty_value].copy()
    audit["source"] = source
    audit["exclusion_reason"] = ""
    audit.loc[invalid_safe, "exclusion_reason"] = "release_availability_unresolved"
    audit.loc[empty_value, "exclusion_reason"] = audit.loc[
        empty_value, "exclusion_reason"
    ].map(lambda value: f"{value};empty_value" if value else "empty_value")

    valid = dataframe.loc[~invalid_safe & ~empty_value].copy()
    if valid.empty:
        raise RuntimeError(f"as-of 결합에 사용할 {source} 유효 관측이 없습니다.")
    if not (valid[observation_column] < valid[safe_column]).all():
        raise RuntimeError(f"{source} 안전 사용일이 관측일보다 늦지 않은 행이 있습니다.")
    states = (
        valid.sort_values([safe_column, observation_column])
        .groupby(safe_column, as_index=False, sort=True)
        .tail(1)
        .sort_values(safe_column)
        .reset_index(drop=True)
    )
    return states, audit


def build_usd_yield_spread_covariates(
    usd_dataframe: pd.DataFrame,
    kr_dataframe: pd.DataFrame,
    us_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """각 USD/KRW 날짜에 그날 안전하게 공개된 최신 유효 한미 금리를 연결한다."""
    usd = validate_weekday_series(usd_dataframe, "USD/KRW").rename(
        columns={"value": "usd_krw_krw_per_usd"}
    )
    kr = validate_kr_yield(kr_dataframe)
    us = validate_us_yield(us_dataframe)
    common_observation_end = min(
        kr["kr_yield_observation_date"].max(),
        us["us_yield_observation_date"].max(),
    )
    # 원시 금리 수집 종료일 뒤로 마지막 상태를 무기한 전달하지 않는다.
    usd = usd.loc[usd["date"] <= common_observation_end].reset_index(drop=True)
    if usd.empty:
        raise RuntimeError("한미 금리 공통 관측 기간 안에 USD/KRW 행이 없습니다.")
    kr_states, kr_audit = latest_available_states(
        kr,
        "kr_yield_observation_date",
        "kr_yield_safe_from_krw_date",
        "kr_treasury_3y_percent",
        "kr_treasury_3y",
    )
    us_states, us_audit = latest_available_states(
        us,
        "us_yield_observation_date",
        "us_yield_safe_from_krw_date",
        "us_treasury_3y_percent",
        "us_treasury_3y",
    )

    aligned = pd.merge_asof(
        usd.sort_values("date"),
        kr_states,
        left_on="date",
        right_on="kr_yield_safe_from_krw_date",
        direction="backward",
        allow_exact_matches=True,
    )
    aligned = pd.merge_asof(
        aligned.sort_values("date"),
        us_states,
        left_on="date",
        right_on="us_yield_safe_from_krw_date",
        direction="backward",
        allow_exact_matches=True,
    )
    aligned = aligned.dropna(
        subset=[
            "kr_treasury_3y_percent",
            "kr_yield_observation_date",
            "kr_yield_safe_from_krw_date",
            "us_treasury_3y_percent",
            "us_yield_observation_date",
            "us_yield_safe_from_krw_date",
        ]
    ).reset_index(drop=True)
    if aligned.empty:
        raise RuntimeError("USD/KRW와 한미 3년물 as-of 결합 결과가 비었습니다.")
    for safe_column in ("kr_yield_safe_from_krw_date", "us_yield_safe_from_krw_date"):
        if not (aligned[safe_column] <= aligned["date"]).all():
            raise RuntimeError("USD/KRW 날짜보다 미래인 금리 안전 사용일이 연결됐습니다.")
    for observation_column in (
        "kr_yield_observation_date",
        "us_yield_observation_date",
    ):
        if not (aligned[observation_column] < aligned["date"]).all():
            raise RuntimeError("USD/KRW 날짜의 현재 또는 미래 금리 관측이 연결됐습니다.")
    if aligned["date"].duplicated().any() or not aligned["date"].is_monotonic_increasing:
        raise RuntimeError("금리차 결합 날짜가 중복됐거나 오름차순이 아닙니다.")
    if aligned["date"].max() > common_observation_end:
        raise RuntimeError("금리 원자료 종료일 뒤의 USD/KRW 날짜가 결합됐습니다.")

    aligned["us_kr_3y_yield_spread_pct_point"] = (
        aligned["us_treasury_3y_percent"] - aligned["kr_treasury_3y_percent"]
    )
    aligned["kr_yield_age_calendar_days"] = (
        aligned["date"] - aligned["kr_yield_observation_date"]
    ).dt.days
    aligned["us_yield_age_calendar_days"] = (
        aligned["date"] - aligned["us_yield_observation_date"]
    ).dt.days
    audit = pd.concat([kr_audit, us_audit], ignore_index=True, sort=False)
    return aligned, audit


def save_without_overwrite(dataframe: pd.DataFrame, path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"기존 한미 금리차 결과를 덮어쓰지 않습니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False, date_format="%Y-%m-%d")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="USD/KRW에 공개시점 기준 한미 3년물 금리차를 연결합니다."
    )
    parser.add_argument("--usd-path", type=Path, default=USD_PATH)
    parser.add_argument("--kr-path", type=Path, default=KR_PATH)
    parser.add_argument("--us-path", type=Path, default=US_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for path in (args.usd_path, args.kr_path, args.us_path):
        if not path.exists():
            raise FileNotFoundError(f"한미 금리차 입력 파일이 없습니다: {path}")
    usd = pd.read_csv(args.usd_path)
    kr = pd.read_csv(args.kr_path, dtype={"stat_code": str, "item_code": str})
    us = pd.read_csv(args.us_path)
    aligned, audit = build_usd_yield_spread_covariates(usd, kr, us)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    period = f"{aligned['date'].min():%Y%m%d}_{aligned['date'].max():%Y%m%d}"
    output_path = PROCESSED_DIR / f"usd_us_kr_3y_yield_spread_asof_{period}_{timestamp}.csv"
    audit_path = (
        PROCESSED_DIR
        / "audit"
        / f"us_kr_3y_yield_excluded_observations_{timestamp}.csv"
    )
    save_without_overwrite(aligned, output_path)
    save_without_overwrite(audit, audit_path)

    print(f"결합 행 수: {len(aligned)}")
    print(f"최초 USD/KRW 날짜: {aligned['date'].min().date()}")
    print(f"최종 USD/KRW 날짜: {aligned['date'].max().date()}")
    print(f"중복 날짜 수: {int(aligned['date'].duplicated().sum())}")
    print(f"한국 금리 제외 관측: {int((audit['source'] == 'kr_treasury_3y').sum())}")
    print(f"미국 금리 제외 관측: {int((audit['source'] == 'us_treasury_3y').sum())}")
    print(f"한국 금리 최대 경과일: {int(aligned['kr_yield_age_calendar_days'].max())}")
    print(f"미국 금리 최대 경과일: {int(aligned['us_yield_age_calendar_days'].max())}")
    print(f"금리차 범위: {aligned['us_kr_3y_yield_spread_pct_point'].min():.6f}~{aligned['us_kr_3y_yield_spread_pct_point'].max():.6f} %p")
    print(f"저장 경로: {output_path}")
    print(f"감사 경로: {audit_path}")


if __name__ == "__main__":
    main()
