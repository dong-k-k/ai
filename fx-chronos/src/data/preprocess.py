from __future__ import annotations

import pandas as pd
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw" / "ecos"
AUDIT_DIR = PROCESSED_DIR / "audit"
FIGURE_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "figures" / "data"


def load_series(csv_path: Path) -> pd.Series:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df[["date", "value"]].copy()
    df = df.dropna()
    df = df.set_index("date")
    return df["value"]


def build_training_series(csv_path: Path) -> pd.Series:
    series = load_series(csv_path)
    return series.astype(float)


def save_preprocessed_series(series: pd.Series, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    series.to_frame(name="value").to_csv(out_path, index=True)


def split_weekday_and_weekend_rows(csv_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split observations without filling, moving, or aggregating any dates."""
    df = pd.read_csv(csv_path, parse_dates=["date"])
    required_columns = {"date", "value"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise RuntimeError(f"필수 열이 없습니다: {sorted(missing_columns)}")
    if df["date"].isna().any():
        raise RuntimeError("날짜로 변환할 수 없는 행이 있습니다.")
    if df["value"].isna().any():
        raise RuntimeError("빈 환율 값이 있습니다.")
    if df["date"].duplicated().any():
        raise RuntimeError("중복 날짜가 있습니다.")

    df = df.sort_values("date").reset_index(drop=True)
    weekend_mask = df["date"].dt.weekday >= 5
    model_df = df.loc[~weekend_mask].copy()
    audit_df = df.loc[weekend_mask].copy()
    audit_df["weekday"] = audit_df["date"].dt.day_name()
    audit_df["exclusion_reason"] = "weekend_observation"

    if len(model_df) + len(audit_df) != len(df):
        raise RuntimeError("모델용 행과 감사 행의 합이 원본 행 수와 다릅니다.")
    return model_df, audit_df


def save_dataframe_without_overwrite(df: pd.DataFrame, out_path: Path) -> None:
    """Save a derived dataset while preserving any existing result."""
    if out_path.exists():
        raise FileExistsError(f"기존 결과 파일을 덮어쓰지 않습니다: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def plot_model_series(csv_path: Path, out_path: Path) -> None:
    """Save a simple full-period plot without changing the model dataset."""
    import matplotlib.pyplot as plt

    if out_path.exists():
        raise FileExistsError(f"기존 그래프를 덮어쓰지 않습니다: {out_path}")

    df = pd.read_csv(csv_path, parse_dates=["date"])
    if df.empty:
        raise RuntimeError("그래프를 생성할 모델용 데이터가 비어 있습니다.")
    if df["date"].isna().any() or df["value"].isna().any():
        raise RuntimeError("그래프 입력에 빈 날짜 또는 환율 값이 있습니다.")
    if not df["date"].is_monotonic_increasing:
        raise RuntimeError("그래프 입력 날짜가 오름차순이 아닙니다.")
    if (df["date"].dt.weekday >= 5).any():
        raise RuntimeError("모델용 데이터에 주말 관측이 포함되어 있습니다.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(14, 6))
    axis.plot(df["date"], df["value"], color="#1f77b4", linewidth=0.8)
    axis.set_title("USD/KRW ECOS Daily Exchange Rate (Weekday Observations)")
    axis.set_xlabel("Observation Date")
    axis.set_ylabel("KRW per USD")
    axis.grid(alpha=0.25)
    axis.text(
        0.01,
        0.98,
        f"{df['date'].min().date()} to {df['date'].max().date()} | {len(df):,} observations",
        transform=axis.transAxes,
        va="top",
    )
    figure.tight_layout()
    figure.savefig(out_path, dpi=150)
    plt.close(figure)


def main() -> None:
    input_path = PROCESSED_DIR / "ecos" / "usdkrw_19640504_20260730.csv"
    model_output_path = PROCESSED_DIR / "usd_krw_model_weekdays_19640504_20260730.csv"
    audit_output_path = AUDIT_DIR / "usd_krw_removed_weekends_19640504_20260730.csv"

    model_df, audit_df = split_weekday_and_weekend_rows(input_path)
    save_dataframe_without_overwrite(model_df, model_output_path)
    save_dataframe_without_overwrite(audit_df, audit_output_path)

    print(f"원본 행 수: {len(model_df) + len(audit_df)}")
    print(f"모델용 월~금 행 수: {len(model_df)}")
    print(f"감사 대상 주말 행 수: {len(audit_df)}")
    print(f"모델용 저장 경로: {model_output_path}")
    print(f"감사 데이터 저장 경로: {audit_output_path}")


if __name__ == "__main__":
    main()
