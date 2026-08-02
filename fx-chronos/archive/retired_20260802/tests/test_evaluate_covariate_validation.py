from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.jpy.evaluate_covariate_validation import evaluate_forecast  # noqa: E402


class EvaluateCovariateValidationTest(unittest.TestCase):
    def test_candidate_passes_only_when_all_fixed_checks_pass(self) -> None:
        rows = []
        for origin_index in range(2):
            for step in range(1, 3):
                actual = 100.0 + step
                rows.append(
                    {
                        "requested_origin": f"2020-0{origin_index + 1}-01",
                        "target_date": pd.Timestamp(2020, origin_index + 1, step + 1),
                        "forecast_step": step,
                        "forecast_origin_value": 100.0,
                        "actual_value": actual,
                        "covariate_q0.1_lower": actual - 2.0,
                        "covariate_q0.5_median": actual,
                        "covariate_q0.9_upper": actual + 2.0,
                        "univariate_q0.5_median": actual + 1.0,
                        "random_walk_forecast": 100.0,
                    }
                )
        forecast = pd.DataFrame(rows)
        criteria = {
            "minimum_origin_mae_wins_vs_univariate": 2,
            "minimum_origin_rmse_wins_vs_univariate": 2,
        }

        _, _, _, _, decision = evaluate_forecast(forecast, criteria)

        self.assertTrue(decision["passed_candidate_entry_criteria"])
        self.assertEqual(
            decision["next_action"],
            "eligible_for_shrunk_ensemble_validation",
        )


if __name__ == "__main__":
    unittest.main()
