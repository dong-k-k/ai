from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.yield_spread.yield_spread_covariate_smoke import (  # noqa: E402
    build_yield_spread_input,
    run_yield_spread_smoke,
)


class FakePipeline:
    quantiles = [0.1, 0.5, 0.9]

    def predict(self, inputs, prediction_length, context_length):
        self.inputs = inputs
        forecast = np.zeros((1, 3, prediction_length), dtype=float)
        forecast[0, 0, :] = 99.0
        forecast[0, 1, :] = 100.0
        forecast[0, 2, :] = 101.0
        return [forecast]


def sample_dataframe(periods: int = 30) -> pd.DataFrame:
    dates = pd.bdate_range("2020-01-01", periods=periods)
    return pd.DataFrame(
        {
            "date": dates,
            "usd_krw_krw_per_usd": np.arange(100.0, 100.0 + periods),
            "kr_yield_observation_date": dates - pd.Timedelta(days=1),
            "kr_yield_safe_from_krw_date": dates,
            "us_yield_observation_date": dates - pd.Timedelta(days=3),
            "us_yield_safe_from_krw_date": dates,
            "us_kr_3y_yield_spread_pct_point": np.linspace(-1.0, 1.0, periods),
        }
    )


class YieldSpreadCovariateSmokeTest(unittest.TestCase):
    def test_input_has_exact_context_and_past_covariate_only(self) -> None:
        dataframe = sample_dataframe()
        requested = dataframe["date"].iloc[20].strftime("%Y-%m-%d")

        model_input, history, origin = build_yield_spread_input(dataframe, requested, 10)

        self.assertEqual(origin, dataframe["date"].iloc[20])
        self.assertEqual(len(history), 10)
        self.assertEqual(len(model_input["target"]), 10)
        self.assertEqual(
            len(model_input["past_covariates"]["us_kr_3y_yield_spread_pct_point"]), 10
        )
        self.assertNotIn("future_covariates", model_input)

    def test_input_rejects_future_safe_date(self) -> None:
        dataframe = sample_dataframe()
        dataframe.loc[10, "us_yield_safe_from_krw_date"] = (
            dataframe.loc[10, "date"] + pd.Timedelta(days=1)
        )
        with self.assertRaisesRegex(RuntimeError, "공개 전"):
            build_yield_spread_input(
                dataframe, dataframe["date"].iloc[20].strftime("%Y-%m-%d"), 15
            )

    def test_smoke_returns_actual_dates_and_ordered_quantiles(self) -> None:
        dataframe = sample_dataframe()
        requested = dataframe["date"].iloc[20].strftime("%Y-%m-%d")

        result = run_yield_spread_smoke(
            FakePipeline(), dataframe, requested, context_length=10, prediction_length=5
        )

        self.assertEqual(len(result), 5)
        self.assertEqual(
            result["target_date"].tolist(), dataframe["date"].iloc[21:26].tolist()
        )
        self.assertEqual(result["chronos_q0.5_median"].tolist(), [100.0] * 5)
        self.assertFalse(result["future_covariates_provided"].iloc[0])


if __name__ == "__main__":
    unittest.main()
