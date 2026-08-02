from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.broad_usd.broad_usd_covariate_smoke import (  # noqa: E402
    build_broad_usd_input,
    run_broad_usd_smoke,
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
            "broad_usd_index": np.arange(110.0, 110.0 + periods),
            "broad_usd_observation_date": dates - pd.Timedelta(days=7),
            "broad_usd_safe_from_krw_date": dates,
        }
    )


class BroadUsdCovariateSmokeTest(unittest.TestCase):
    def test_input_includes_requested_origin_and_exact_context(self) -> None:
        dataframe = sample_dataframe()
        requested = dataframe["date"].iloc[20].strftime("%Y-%m-%d")

        model_input, history, origin = build_broad_usd_input(dataframe, requested, 10)

        self.assertEqual(origin, dataframe["date"].iloc[20])
        self.assertEqual(len(history), 10)
        self.assertEqual(len(model_input["target"]), 10)
        self.assertEqual(len(model_input["past_covariates"]["broad_usd_index_asof"]), 10)

    def test_input_rejects_future_safe_date(self) -> None:
        dataframe = sample_dataframe()
        dataframe.loc[10, "broad_usd_safe_from_krw_date"] = dataframe.loc[10, "date"] + pd.Timedelta(days=1)
        with self.assertRaisesRegex(RuntimeError, "공개 전"):
            build_broad_usd_input(dataframe, dataframe["date"].iloc[20].strftime("%Y-%m-%d"), 15)

    def test_smoke_returns_actual_dates_and_quantiles(self) -> None:
        dataframe = sample_dataframe()
        requested = dataframe["date"].iloc[20].strftime("%Y-%m-%d")

        result = run_broad_usd_smoke(
            FakePipeline(), dataframe, requested, context_length=10, prediction_length=5
        )

        self.assertEqual(len(result), 5)
        self.assertEqual(result["target_date"].tolist(), dataframe["date"].iloc[21:26].tolist())
        self.assertEqual(result["chronos_q0.5_median"].tolist(), [100.0] * 5)
        self.assertFalse(result["future_covariates_provided"].iloc[0])


if __name__ == "__main__":
    unittest.main()
