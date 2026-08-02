from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.log_return.log_return_smoke import (  # noqa: E402
    build_log_return_input,
    levels_to_log_returns,
    reconstruct_levels,
    run_log_return_smoke,
)


class FakePipeline:
    quantiles = [0.1, 0.5, 0.9]

    def predict(self, inputs, prediction_length, context_length, cross_learning):
        self.inputs = inputs
        self.context_length = context_length
        self.cross_learning = cross_learning
        forecast = np.zeros((1, 3, prediction_length), dtype=np.float32)
        forecast[0, 1, :] = np.log(1.01)
        return [forecast]


class LogReturnSmokeTest(unittest.TestCase):
    def test_log_return_round_trip_restores_levels(self) -> None:
        levels = np.array([100.0, 101.0, 99.0, 102.0])
        restored = reconstruct_levels(levels[0], levels_to_log_returns(levels))
        np.testing.assert_allclose(restored, levels[1:])

    def test_log_return_rejects_nonpositive_level(self) -> None:
        with self.assertRaises(ValueError):
            levels_to_log_returns(np.array([100.0, 0.0, 101.0]))

    def test_input_includes_observation_on_requested_origin(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=30)
        dataframe = pd.DataFrame({"date": dates, "value": np.arange(100.0, 130.0)})
        requested_origin = dates[20].strftime("%Y-%m-%d")

        log_returns, origin_index = build_log_return_input(
            dataframe,
            requested_origin=requested_origin,
            context_length=10,
            prediction_length=5,
        )

        self.assertEqual(origin_index, 20)
        self.assertEqual(len(log_returns), 10)
        expected = np.log(dataframe.loc[20, "value"] / dataframe.loc[19, "value"])
        self.assertAlmostEqual(float(log_returns[-1]), float(expected), places=7)

    def test_smoke_reconstructs_median_and_uses_actual_dates(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=30)
        dataframe = pd.DataFrame({"date": dates, "value": np.full(30, 100.0)})
        pipeline = FakePipeline()

        result = run_log_return_smoke(
            pipeline,
            dataframe,
            requested_origin=dates[20].strftime("%Y-%m-%d"),
            context_length=10,
            prediction_length=5,
        )

        self.assertEqual(len(result), 5)
        np.testing.assert_allclose(
            result["reconstructed_chronos_q0.5"],
            100.0 * np.power(1.01, np.arange(1, 6)),
        )
        self.assertEqual(result["target_date"].tolist(), dates[21:26].tolist())
        self.assertEqual(len(pipeline.inputs[0]), 10)
        self.assertFalse(pipeline.cross_learning)


if __name__ == "__main__":
    unittest.main()
