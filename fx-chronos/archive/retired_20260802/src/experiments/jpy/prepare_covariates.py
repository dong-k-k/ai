from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
USD_PATH = (
    PROJECT_DIR / "data" / "processed" / "usd_krw_model_weekdays_19640504_20260730.csv"
)
JPY_PATH = (
    PROJECT_DIR / "data" / "processed" / "jpy_krw_model_weekdays_19770401_20260730.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "data"
    / "processed"
    / "usd_jpy_covariates_weekdays_lag1_19770404_20260730.csv"
)


def validate_weekday_series(dataframe: pd.DataFrame, series_name: str) -> pd.DataFrame:
    """Validate one model series without filling or changing observation dates."""
    required_columns = {"date", "value"}
    missing_columns = required_columns - set(dataframe.columns)
    if missing_columns:
        raise RuntimeError(f"{series_name} 필수 열이 없습니다: {sorted(missing_columns)}")

    validated = dataframe[["date", "value"]].copy()
    validated["date"] = pd.to_datetime(validated["date"], errors="coerce")
    validated["value"] = pd.to_numeric(validated["value"], errors="coerce")
    if validated[["date", "value"]].isna().any().any():
        raise RuntimeError(f"{series_name} 날짜 또는 값에 결측·변환 실패가 있습니다.")
    if validated["date"].duplicated().any():
        raise RuntimeError(f"{series_name}에 중복 날짜가 있습니다.")
    if (validated["date"].dt.weekday >= 5).any():
        raise RuntimeError(f"{series_name}에 주말 관측이 포함되어 있습니다.")

    return validated.sort_values("date").reset_index(drop=True)


def build_usd_jpy_covariates(
    usd_dataframe: pd.DataFrame,
    jpy_dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Align USD/KRW with a one-common-observation-lagged JPY/KRW covariate."""
    usd = validate_weekday_series(usd_dataframe, "USD/KRW").rename(
        columns={"value": "usd_krw_krw_per_usd"}
    )
    jpy = validate_weekday_series(jpy_dataframe, "JPY/KRW").rename(
        columns={"value": "jpy_krw_same_date_audit_only"}
    )

    aligned = usd.merge(jpy, on="date", how="inner", validate="one_to_one")
    aligned = aligned.sort_values("date").reset_index(drop=True)
    if aligned.empty:
        raise RuntimeError("USD/KRW와 JPY/KRW의 공통 관측일이 없습니다.")

    # 정확한 당일 공개 시각이 확인되지 않았으므로 직전 공통 관측값만 모델 입력으로 사용한다.
    aligned["jpy_krw_krw_per_jpy_lag1"] = aligned[
        "jpy_krw_same_date_audit_only"
    ].shift(1)
    aligned["jpy_source_date_lag1"] = aligned["date"].shift(1)
    aligned = aligned.dropna(
        subset=["jpy_krw_krw_per_jpy_lag1", "jpy_source_date_lag1"]
    ).reset_index(drop=True)

    if not (aligned["jpy_source_date_lag1"] < aligned["date"]).all():
        raise RuntimeError("JPY/KRW 공변량에 현재 또는 미래 관측값이 포함되어 있습니다.")
    if aligned["date"].duplicated().any() or not aligned["date"].is_monotonic_increasing:
        raise RuntimeError("정렬 결과 날짜가 중복됐거나 오름차순이 아닙니다.")
    return aligned


def save_without_overwrite(dataframe: pd.DataFrame, output_path: Path) -> None:
    if output_path.exists():
        raise FileExistsError(f"기존 공변량 데이터를 덮어쓰지 않습니다: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_csv(output_path, index=False, date_format="%Y-%m-%d")


def main() -> None:
    usd = pd.read_csv(USD_PATH)
    jpy = pd.read_csv(JPY_PATH)
    aligned = build_usd_jpy_covariates(usd, jpy)
    save_without_overwrite(aligned, OUTPUT_PATH)

    print(f"공통 날짜 정렬 후 lag1 행 수: {len(aligned)}")
    print(f"최초 타깃 날짜: {aligned['date'].min().date()}")
    print(f"최종 타깃 날짜: {aligned['date'].max().date()}")
    print("모델용 JPY 정책: 직전 실제 공통 관측값(lag1), 채움·보간 없음")
    print(f"저장 경로: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
