from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parent.parent
MODEL_DATA_PATH = PROJECT_DIR / "data" / "processed" / "usd_krw_model_weekdays_19640504_20260730.csv"
BACKTEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "forecasts"
    / "usd_krw_walk_forward_h20_monthly_1997_2025.csv"
)
SPLIT_MANIFEST_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "usd_krw_walk_forward_h20_monthly_1997_2025_split_manifest.csv"
)
OUTPUT_PATH = (
    PROJECT_DIR
    / "outputs"
    / "metrics"
    / "usd_krw_chronos2_finetuning_data_manifest.csv"
)
TRAIN_TARGET_END = pd.Timestamp("2017-12-31")
PREDICTION_LENGTH = 20
EXPECTED_VALIDATION_ORIGINS = 48


def load_model_data(path: Path) -> pd.DataFrame:
    """Load the immutable weekday observation sequence used by the project."""
    data = pd.read_csv(path, parse_dates=["date"])
    if data.empty or data[["date", "value"]].isna().any().any():
        raise RuntimeError("파인튜닝 원본 모델 데이터가 비어 있거나 결측값이 있습니다.")
    data = data.sort_values("date").reset_index(drop=True)
    if data["date"].duplicated().any():
        raise RuntimeError("파인튜닝 원본 모델 데이터에 중복 날짜가 있습니다.")
    if (data["date"].dt.weekday >= 5).any():
        raise RuntimeError("파인튜닝 원본 모델 데이터에 주말 관측이 있습니다.")
    return data[["date", "value"]].copy()


def build_finetuning_inputs(
    model_data: pd.DataFrame,
    backtest: pd.DataFrame,
    split_manifest: pd.DataFrame,
) -> tuple[list[np.ndarray], list[np.ndarray], pd.DataFrame]:
    """Build one training series and leak-free walk-forward Validation sequences."""
    train = model_data.loc[model_data["date"] <= TRAIN_TARGET_END].copy()
    if train.empty or train["date"].max() > TRAIN_TARGET_END:
        raise RuntimeError("학습 시계열 종료일 검증에 실패했습니다.")
    train_inputs = [train["value"].to_numpy(dtype=np.float32)]

    validation_origins = split_manifest.loc[
        split_manifest["split"].eq("validation"), "requested_origin"
    ].tolist()
    if len(validation_origins) != EXPECTED_VALIDATION_ORIGINS:
        raise RuntimeError(
            f"Validation 기준일 수가 예상과 다릅니다: "
            f"실제={len(validation_origins)}, 예상={EXPECTED_VALIDATION_ORIGINS}"
        )

    date_to_index = pd.Series(model_data.index, index=model_data["date"])
    validation_inputs: list[np.ndarray] = []
    audit_rows: list[dict[str, object]] = [
        {
            "dataset_role": "train",
            "requested_origin": "",
            "context_start": train["date"].iloc[0],
            "forecast_origin_date": train["date"].iloc[-1],
            "target_start": "",
            "target_end": train["date"].iloc[-1],
            "context_rows": len(train),
            "target_rows": 0,
            "total_rows": len(train),
        }
    ]

    for requested_origin in validation_origins:
        origin_rows = backtest.loc[
            backtest["requested_origin"].eq(requested_origin)
        ].sort_values("forecast_step")
        if len(origin_rows) != PREDICTION_LENGTH:
            raise RuntimeError(f"Validation 예측 행이 20개가 아닙니다: {requested_origin}")
        if origin_rows["forecast_step"].tolist() != list(range(1, PREDICTION_LENGTH + 1)):
            raise RuntimeError(f"Validation forecast_step이 연속적이지 않습니다: {requested_origin}")

        origin_date = pd.Timestamp(origin_rows["forecast_origin_date"].iloc[0])
        target_dates = pd.DatetimeIndex(origin_rows["target_date"])
        if origin_date not in date_to_index.index or not target_dates.isin(date_to_index.index).all():
            raise RuntimeError(f"모델 데이터에서 Validation 날짜를 찾을 수 없습니다: {requested_origin}")

        origin_index = int(date_to_index.loc[origin_date])
        target_indices = date_to_index.loc[target_dates].to_numpy(dtype=int)
        expected_indices = np.arange(origin_index + 1, origin_index + PREDICTION_LENGTH + 1)
        if not np.array_equal(target_indices, expected_indices):
            raise RuntimeError(f"Validation 목표 날짜가 다음 20개 실제 관측이 아닙니다: {requested_origin}")

        sequence = model_data.iloc[: origin_index + PREDICTION_LENGTH + 1]
        expected_actual = origin_rows["actual_value"].to_numpy(dtype=float)
        sequence_target = sequence["value"].tail(PREDICTION_LENGTH).to_numpy(dtype=float)
        if not np.array_equal(sequence_target, expected_actual):
            raise RuntimeError(f"Validation 실제값이 모델 데이터와 다릅니다: {requested_origin}")

        validation_inputs.append(sequence["value"].to_numpy(dtype=np.float32))
        audit_rows.append(
            {
                "dataset_role": "validation",
                "requested_origin": requested_origin,
                "context_start": sequence["date"].iloc[0],
                "forecast_origin_date": origin_date,
                "target_start": target_dates[0],
                "target_end": target_dates[-1],
                "context_rows": origin_index + 1,
                "target_rows": PREDICTION_LENGTH,
                "total_rows": len(sequence),
            }
        )

    return train_inputs, validation_inputs, pd.DataFrame.from_records(audit_rows)


def main() -> None:
    if OUTPUT_PATH.exists():
        raise FileExistsError(f"기존 파인튜닝 데이터 명세를 덮어쓰지 않습니다: {OUTPUT_PATH}")

    model_data = load_model_data(MODEL_DATA_PATH)
    backtest = pd.read_csv(
        BACKTEST_PATH,
        parse_dates=["forecast_origin_date", "target_date"],
    )
    split_manifest = pd.read_csv(SPLIT_MANIFEST_PATH)
    train_inputs, validation_inputs, audit = build_finetuning_inputs(
        model_data,
        backtest,
        split_manifest,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    audit.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")

    print(f"Saved fine-tuning data manifest to {OUTPUT_PATH}")
    print(f"Training series: {len(train_inputs)}, rows: {len(train_inputs[0])}")
    print(f"Validation series: {len(validation_inputs)}")
    print(f"Prediction length: {PREDICTION_LENGTH}")


if __name__ == "__main__":
    main()
