from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.broad_usd.evaluate_broad_usd_validation import evaluate_forecast  # noqa: E402


class EvaluateBroadUsdValidationTest(unittest.TestCase):
    def test_candidate_passes_only_when_all_locked_checks_pass(self) -> None:
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
                        "covariate_q0.1_lower": 101.0,
                        "covariate_q0.5_median": 101.9,
                        "covariate_q0.9_upper": 103.0,
                        "univariate_q0.5_median": 101.0,
                        "random_walk_forecast": 100.0,
                    }
                )
        criteria = {
            "minimum_origin_mae_wins_vs_univariate": 25,
            "minimum_origin_rmse_wins_vs_univariate": 25,
        }

        _, _, _, _, decision = evaluate_forecast(pd.DataFrame(rows), criteria)

        self.assertTrue(decision["passed_candidate_entry_criteria"])
        self.assertFalse(decision["final_test_2022_2025_used"])

    def test_candidate_fails_when_random_walk_is_better(self) -> None:
        rows = []
        for origin_index in range(48):
            rows.append(
                {
                    "requested_origin": f"origin-{origin_index:02d}",
                    "target_date": pd.Timestamp("2020-01-01"),
                    "forecast_step": 1,
                    "forecast_origin_value": 100.0,
                    "actual_value": 100.0,
                    "covariate_q0.1_lower": 98.0,
                    "covariate_q0.5_median": 101.0,
                    "covariate_q0.9_upper": 102.0,
                    "univariate_q0.5_median": 102.0,
                    "random_walk_forecast": 100.0,
                }
            )
        criteria = {
            "minimum_origin_mae_wins_vs_univariate": 25,
            "minimum_origin_rmse_wins_vs_univariate": 25,
        }

        _, _, _, _, decision = evaluate_forecast(pd.DataFrame(rows), criteria)

        self.assertFalse(decision["passed_candidate_entry_criteria"])
        self.assertFalse(decision["criteria_checks"]["lower_mae_than_random_walk"])


if __name__ == "__main__":
    unittest.main()
