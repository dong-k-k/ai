from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.jpy.covariate_smoke import build_past_covariate_input, run_covariate_smoke  # noqa: E402


class FakePipeline:
    quantiles = [0.1, 0.5, 0.9]

    def __init__(self) -> None:
        self.received_inputs: list[dict[str, object]] | None = None

    def predict(
        self,
        inputs: list[dict[str, object]],
        prediction_length: int,
        context_length: int,
    ) -> list[np.ndarray]:
        self.received_inputs = inputs
        self.context_length = context_length
        values = np.stack(
            [
                np.full(prediction_length, 1300.0),
                np.full(prediction_length, 1350.0),
                np.full(prediction_length, 1400.0),
            ]
        )
        return [values.reshape(1, 3, prediction_length)]


def sample_dataframe(rows: int = 30) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=rows)
    return pd.DataFrame(
        {
            "date": dates,
            "usd_krw_krw_per_usd": np.arange(rows, dtype=float) + 1300.0,
            "jpy_krw_krw_per_jpy_lag1": np.arange(rows, dtype=float) + 9.0,
            "jpy_source_date_lag1": dates - pd.offsets.BDay(1),
        }
    )


class CovariateSmokeTest(unittest.TestCase):
    def test_builds_target_and_past_covariate_without_future_covariates(self) -> None:
        dataframe = sample_dataframe()
        requested_origin = dataframe["date"].iloc[20].strftime("%Y-%m-%d")

        model_input, history, forecast_origin = build_past_covariate_input(
            dataframe,
            requested_origin,
            context_length=10,
        )

        self.assertEqual(set(model_input), {"target", "past_covariates"})
        self.assertNotIn("future_covariates", model_input)
        self.assertEqual(len(model_input["target"]), 10)
        self.assertEqual(len(model_input["past_covariates"]["jpy_krw_lag1"]), 10)
        self.assertEqual(forecast_origin, history["date"].iloc[-1])
        self.assertEqual(forecast_origin, dataframe["date"].iloc[20])
        self.assertTrue((history["jpy_source_date_lag1"] < history["date"]).all())

    def test_smoke_returns_only_usd_target_forecast(self) -> None:
        dataframe = sample_dataframe()
        pipeline = FakePipeline()
        requested_origin = dataframe["date"].iloc[10].strftime("%Y-%m-%d")

        result = run_covariate_smoke(
            pipeline,
            dataframe,
            requested_origin=requested_origin,
            context_length=10,
            prediction_length=5,
        )

        self.assertEqual(len(result), 5)
        self.assertEqual(result["target_series"].unique().tolist(), ["USD/KRW"])
        self.assertFalse(result["future_covariates_provided"].any())
        self.assertEqual(pipeline.context_length, 10)
        self.assertNotIn("future_covariates", pipeline.received_inputs[0])
        self.assertTrue(
            (result["chronos_q0.1_lower"] <= result["chronos_q0.5_median"]).all()
        )
        self.assertTrue(
            (result["chronos_q0.5_median"] <= result["chronos_q0.9_upper"]).all()
        )

    def test_rejects_same_date_jpy_source(self) -> None:
        dataframe = sample_dataframe()
        dataframe["jpy_source_date_lag1"] = dataframe["date"]

        with self.assertRaisesRegex(RuntimeError, "현재 또는 미래"):
            build_past_covariate_input(
                dataframe,
                requested_origin="2026-02-01",
                context_length=5,
            )


if __name__ == "__main__":
    unittest.main()
