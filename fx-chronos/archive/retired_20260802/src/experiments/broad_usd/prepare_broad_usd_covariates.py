from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.experiments.jpy.prepare_covariates import validate_weekday_series


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
USD_PATH = (
    PROJECT_DIR / "data" / "processed" / "usd_krw_model_weekdays_19640504_20260730.csv"
)
BROAD_USD_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "fred"
    / "broad_usd_index_availability_20060102_20260724_20260802T074709Z.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_broad_usd_covariates_weekdays_asof_20090114_20260730.csv"
)
AUDIT_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "audit"
    / "broad_usd_excluded_observations_20060102_20260724.csv"
)


def validate_broad_usd_availability(dataframe: pd.DataFrame) -> pd.DataFrame:
    required = {
        "date",
        "broad_usd_index",
        "series_id",
        "unit",
        "frequency",
        "h10_release_date",
        "available_at_et",
        "available_at_kst",
        "safe_from_krw_date",
        "release_regime",
        "availability_rule",
    }
    missing = required - set(dataframe.columns)
    if missing:
        raise RuntimeError(f"Broad Dollar 공개시점 데이터에 필수 열이 없습니다: {sorted(missing)}")
    validated = dataframe[list(required)].copy()
    validated = validated.rename(columns={"date": "broad_usd_observation_date"})
    validated["broad_usd_observation_date"] = pd.to_datetime(
        validated["broad_usd_observation_date"], errors="coerce"
    )
    validated["broad_usd_index"] = pd.to_numeric(
        validated["broad_usd_index"], errors="coerce"
    )
    validated["h10_release_date"] = pd.to_datetime(
        validated["h10_release_date"], errors="coerce"
    )
    validated["safe_from_krw_date"] = pd.to_datetime(
        validated["safe_from_krw_date"], errors="coerce"
    )
    if validated["broad_usd_observation_date"].isna().any():
        raise RuntimeError("Broad Dollar에 변환할 수 없는 관측 날짜가 있습니다.")
    if validated["broad_usd_observation_date"].duplicated().any():
        raise RuntimeError("Broad Dollar에 중복 관측 날짜가 있습니다.")
    return validated.sort_values("broad_usd_observation_date").reset_index(drop=True)


def build_usd_broad_usd_covariates(
    usd_dataframe: pd.DataFrame,
    broad_dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """공식 공개가 끝난 최신 유효 Broad Dollar 관측만 USD/KRW에 연결한다."""
    usd = validate_weekday_series(usd_dataframe, "USD/KRW").rename(
        columns={"value": "usd_krw_krw_per_usd"}
    )
    broad = validate_broad_usd_availability(broad_dataframe)

    unresolved = broad["safe_from_krw_date"].isna()
    empty_value = broad["broad_usd_index"].isna()
    audit = broad.loc[unresolved | empty_value].copy()
    audit["exclusion_reason"] = ""
    audit.loc[unresolved, "exclusion_reason"] = "release_availability_unresolved"
    audit.loc[empty_value, "exclusion_reason"] = audit.loc[
        empty_value, "exclusion_reason"
    ].map(lambda value: f"{value};empty_value" if value else "empty_value")

    valid = broad.loc[~unresolved & ~empty_value].copy()
    if valid.empty:
        raise RuntimeError("as-of 결합에 사용할 Broad Dollar 유효 관측이 없습니다.")
    if not (
        valid["broad_usd_observation_date"] < valid["safe_from_krw_date"]
    ).all():
        raise RuntimeError("Broad Dollar 안전 사용일이 관측일보다 늦지 않은 행이 있습니다.")

    # 한 H.10 공개 묶음에서는 가장 최근의 실제 유효 관측 하나만 현재 상태로 사용한다.
    available_states = (
        valid.sort_values(["safe_from_krw_date", "broad_usd_observation_date"])
        .groupby("safe_from_krw_date", as_index=False, sort=True)
        .tail(1)
        .sort_values("safe_from_krw_date")
        .reset_index(drop=True)
    )
    aligned = pd.merge_asof(
        usd.sort_values("date"),
        available_states,
        left_on="date",
        right_on="safe_from_krw_date",
        direction="backward",
        allow_exact_matches=True,
    )
    aligned = aligned.dropna(
        subset=["broad_usd_index", "broad_usd_observation_date", "safe_from_krw_date"]
    ).reset_index(drop=True)
    if aligned.empty:
        raise RuntimeError("USD/KRW와 Broad Dollar의 as-of 결합 결과가 비어 있습니다.")
    if not (aligned["safe_from_krw_date"] <= aligned["date"]).all():
        raise RuntimeError("USD/KRW 날짜보다 미래인 안전 사용일이 연결됐습니다.")
    if not (aligned["broad_usd_observation_date"] < aligned["date"]).all():
        raise RuntimeError("USD/KRW 날짜의 현재 또는 미래 Broad Dollar 관측이 연결됐습니다.")
    if aligned["date"].duplicated().any() or not aligned["date"].is_monotonic_increasing:
        raise RuntimeError("as-of 결합 날짜가 중복됐거나 오름차순이 아닙니다.")

    aligned["broad_usd_age_calendar_days"] = (
        aligned["date"] - aligned["broad_usd_observation_date"]
    ).dt.days
    aligned = aligned.rename(
        columns={
            "h10_release_date": "broad_usd_h10_release_date",
            "available_at_et": "broad_usd_available_at_et",
            "available_at_kst": "broad_usd_available_at_kst",
            "safe_from_krw_date": "broad_usd_safe_from_krw_date",
            "series_id": "broad_usd_series_id",
            "unit": "broad_usd_unit",
            "frequency": "broad_usd_frequency",
        }
    )
    return aligned, audit


def save_without_overwrite(dataframe: pd.DataFrame, path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"기존 Broad Dollar 결합 결과를 덮어쓰지 않습니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(path, index=False, date_format="%Y-%m-%d")


def main() -> None:
    output_paths = (OUTPUT_PATH, AUDIT_PATH)
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise FileExistsError(f"기존 Broad Dollar 결합 결과를 덮어쓰지 않습니다: {existing}")
    usd = pd.read_csv(USD_PATH)
    broad = pd.read_csv(BROAD_USD_PATH)
    aligned, audit = build_usd_broad_usd_covariates(usd, broad)
    save_without_overwrite(aligned, OUTPUT_PATH)
    save_without_overwrite(audit, AUDIT_PATH)

    validation_context = aligned[aligned["date"] >= pd.Timestamp("2015-01-01")]
    print(f"결합 행 수: {len(aligned)}")
    print(f"최초 USD/KRW 날짜: {aligned['date'].min().date()}")
    print(f"최종 USD/KRW 날짜: {aligned['date'].max().date()}")
    print(f"Broad Dollar 제외 관측 행 수: {len(audit)}")
    print(
        "2015년 이후 공변량 결측 행 수: "
        f"{int(validation_context['broad_usd_index'].isna().sum())}"
    )
    print(f"최대 공변량 경과일: {int(aligned['broad_usd_age_calendar_days'].max())}")
    print(f"저장 경로: {OUTPUT_PATH}")
    print(f"감사 경로: {AUDIT_PATH}")


if __name__ == "__main__":
    main()
