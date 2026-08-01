from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from chronos import Chronos2Pipeline


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "forecasts"
MODEL_ID = "amazon/chronos-2"
HORIZON = 20
EXPANSION_HORIZONS = (60,)
CONTEXT_LENGTH = 8192
BATCH_SIZE = 8
REQUESTED_ORIGINS = [
    "1997-11-03",
    "2008-09-01",
    "2020-03-02",
    "2022-09-01",
    "2025-12-01",
]


def build_semiannual_origins(start_year: int, end_year: int) -> list[str]:
    """Build two requested forecast origins per year without inspecting future values."""
    if start_year > end_year:
        raise ValueError("start_year는 end_year보다 늦을 수 없습니다.")
    origins: list[str] = []
    for year in range(start_year, end_year + 1):
        origins.extend([f"{year}-01-02", f"{year}-07-01"])
    return origins


def load_model_data(csv_path: Path) -> pd.DataFrame:
    """Load and validate the weekday-only series in chronological order."""
    df = pd.read_csv(csv_path, parse_dates=["date"])
    if df.empty:
        raise RuntimeError("백테스트 입력 데이터가 비어 있습니다.")
    if df[["date", "value"]].isna().any().any():
        raise RuntimeError("백테스트 입력에 빈 날짜 또는 환율 값이 있습니다.")
    if df["date"].duplicated().any():
        raise RuntimeError("백테스트 입력에 중복 날짜가 있습니다.")

    df = df.sort_values("date").reset_index(drop=True)
    if (df["date"].dt.weekday >= 5).any():
        raise RuntimeError("백테스트 입력에 주말 관측이 포함되어 있습니다.")
    return df[["date", "value"]].copy()


def resolve_origin_index(df: pd.DataFrame, requested_origin: str, horizon: int) -> int:
    """Use the latest actual observation on or before the requested date."""
    requested_date = pd.Timestamp(requested_origin)
    candidates = df.index[df["date"] <= requested_date]
    if len(candidates) == 0:
        raise RuntimeError(f"기준일 이전 관측이 없습니다: {requested_origin}")

    origin_index = int(candidates[-1])
    if origin_index + horizon >= len(df):
        raise RuntimeError(f"기준일 이후 실제 관측이 {horizon}개보다 적습니다: {requested_origin}")
    return origin_index


def find_quantile_index(quantile_levels: list[float], target: float) -> int:
    for index, level in enumerate(quantile_levels):
        if abs(float(level) - target) < 1e-8:
            return index
    raise RuntimeError(f"모델 출력에 필요한 분위수 {target}이 없습니다: {quantile_levels}")


def run_walk_forward_backtest(
    pipeline: Chronos2Pipeline,
    df: pd.DataFrame,
    requested_origins: list[str],
    horizon: int,
    context_length: int,
    batch_size: int = 256,
) -> pd.DataFrame:
    """Forecast multiple historical origins without using observations after each origin."""
    origin_indices = [resolve_origin_index(df, origin, horizon) for origin in requested_origins]
    model_inputs = [
        df.loc[:origin_index, "value"].to_numpy(dtype=np.float32)
        for origin_index in origin_indices
    ]
    predictions = pipeline.predict(
        model_inputs,
        prediction_length=horizon,
        batch_size=batch_size,
        context_length=context_length,
        cross_learning=False,
    )
    if len(predictions) != len(origin_indices):
        raise RuntimeError(
            f"예측 결과 수가 기준일 수와 다릅니다: 예측={len(predictions)}, 기준일={len(origin_indices)}"
        )

    quantile_levels = [float(level) for level in pipeline.quantiles]
    q10_index = find_quantile_index(quantile_levels, 0.1)
    q50_index = find_quantile_index(quantile_levels, 0.5)
    q90_index = find_quantile_index(quantile_levels, 0.9)
    records: list[dict[str, object]] = []

    for requested_origin, origin_index, prediction in zip(
        requested_origins,
        origin_indices,
        predictions,
        strict=True,
    ):
        forecast = prediction.detach().cpu().numpy()
        expected_shape = (1, len(quantile_levels), horizon)
        if forecast.shape != expected_shape:
            raise RuntimeError(f"예상하지 못한 예측 shape: 실제={forecast.shape}, 예상={expected_shape}")

        q10 = forecast[0, q10_index, :]
        q50 = forecast[0, q50_index, :]
        q90 = forecast[0, q90_index, :]
        if not np.all((q10 <= q50) & (q50 <= q90)):
            raise RuntimeError(f"분위수 순서가 올바르지 않습니다: {requested_origin}")

        history = df.loc[:origin_index, "value"].astype(float)
        origin_date = pd.Timestamp(df.loc[origin_index, "date"])
        origin_value = float(df.loc[origin_index, "value"])
        actual_future = df.iloc[origin_index + 1 : origin_index + horizon + 1]
        mase_scale = float(history.diff().abs().dropna().mean())
        if not np.isfinite(mase_scale) or mase_scale <= 0:
            raise RuntimeError(f"MASE 분모를 계산할 수 없습니다: {requested_origin}")

        for step, (_, actual_row) in enumerate(actual_future.iterrows(), start=1):
            records.append(
                {
                    "requested_origin": requested_origin,
                    "forecast_origin_date": origin_date.date().isoformat(),
                    "forecast_origin_value": origin_value,
                    "forecast_step": step,
                    "target_date": pd.Timestamp(actual_row["date"]).date().isoformat(),
                    "actual_value": float(actual_row["value"]),
                    "chronos_q0.1_lower": float(q10[step - 1]),
                    "chronos_q0.5_median": float(q50[step - 1]),
                    "chronos_q0.9_upper": float(q90[step - 1]),
                    "random_walk_forecast": origin_value,
                    "history_rows": origin_index + 1,
                    "context_length": min(context_length, origin_index + 1),
                    "mase_scale_training_only": mase_scale,
                    "model_id": MODEL_ID,
                }
            )

    return pd.DataFrame.from_records(records)


def main() -> None:
    input_path = PROCESSED_DIR / "usd_krw_model_weekdays_19640504_20260730.csv"
    output_paths = {
        horizon: OUTPUT_DIR / f"usd_krw_walk_forward_h{horizon}_semiannual_1997_2025.csv"
        for horizon in EXPANSION_HORIZONS
    }
    for output_path in output_paths.values():
        if output_path.exists():
            raise FileExistsError(f"기존 백테스트 결과를 덮어쓰지 않습니다: {output_path}")

    df = load_model_data(input_path)
    requested_origins = build_semiannual_origins(1997, 2025)
    for horizon in EXPANSION_HORIZONS:
        resolved_indices = [
            resolve_origin_index(df, requested_origin, horizon)
            for requested_origin in requested_origins
        ]
        if len(set(resolved_indices)) != len(resolved_indices):
            raise RuntimeError(
                f"서로 다른 요청 기준일이 같은 실제 관측일로 중복 해석되었습니다: horizon={horizon}"
            )

    pipeline = Chronos2Pipeline.from_pretrained(MODEL_ID)
    for horizon in EXPANSION_HORIZONS:
        result = run_walk_forward_backtest(
            pipeline,
            df,
            requested_origins=requested_origins,
            horizon=horizon,
            context_length=CONTEXT_LENGTH,
            batch_size=BATCH_SIZE,
        )
        output_path = output_paths[horizon]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output_path, index=False)

        print(f"Saved walk-forward backtest to {output_path}")
        print(f"Horizon: {horizon}")
        print(f"Forecast origins: {result['forecast_origin_date'].nunique()}")
        print(f"Rows: {len(result)}")


if __name__ == "__main__":
    main()
