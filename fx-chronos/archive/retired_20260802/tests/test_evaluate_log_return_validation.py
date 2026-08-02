from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.log_return.evaluate_log_return_validation import evaluate_forecast, forecasts_to_dataframe  # noqa: E402


class EvaluateLogReturnValidationTest(unittest.TestCase):
    def test_forecast_reconstructs_level_from_each_origin(self) -> None:
        group = pd.DataFrame(
            {
                "requested_origin": ["2020-01-01"] * 2,
                "forecast_origin_date": pd.to_datetime(["2020-01-01"] * 2),
                "forecast_origin_value": [100.0] * 2,
                "forecast_step": [1, 2],
                "target_date": pd.to_datetime(["2020-01-02", "2020-01-03"]),
                "actual_value": [101.0, 102.0],
                "chronos_q0.5_median": [100.5, 101.5],
                "random_walk_forecast": [100.0, 100.0],
            }
        )
        prediction = np.zeros((1, 3, 2), dtype=float)
        prediction[0, 1, :] = np.log(1.01)

        result = forecasts_to_dataframe(
            [prediction], [group], [100.0], [0.1, 0.5, 0.9], 10, 2
        )

        np.testing.assert_allclose(
            result["log_return_reconstructed_q0.5"], [101.0, 102.01]
        )

    def test_decision_requires_all_locked_checks(self) -> None:
        rows = []
        for origin_index in range(48):
            for step in range(1, 3):
                rows.append(
                    {
                        "requested_origin": f"origin-{origin_index:02d}",
                        "target_date": pd.Timestamp("2020-01-01"),
                        "forecast_step": step,
                        "forecast_origin_value": 100.0,
                        "actual_value": 102.0,
                        "log_return_reconstructed_q0.5": 101.9,
                        "level_chronos_q0.5_median": 101.0,
                        "random_walk_forecast": 100.0,
                    }
                )
        forecast = pd.DataFrame(rows)
        criteria = {
            "minimum_origin_mae_wins_vs_level_chronos": 25,
            "minimum_origin_rmse_wins_vs_level_chronos": 25,
        }

        _, _, _, _, decision = evaluate_forecast(forecast, criteria)

        self.assertTrue(decision["passed_candidate_entry_criteria"])
        self.assertFalse(decision["final_test_2022_2025_used"])
        self.assertFalse(decision["intervals_evaluated"])


if __name__ == "__main__":
    unittest.main()
