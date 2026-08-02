from __future__ import annotations

import unittest

import pandas as pd

from src.evaluation.evaluate_h90_locked_ensemble import evaluate_forecast


def rows(ensemble_value: float, actual_value: float = 102.0) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "requested_origin": f"origin-{index:02d}",
            "forecast_step": 1,
            "forecast_origin_value": 100.0,
            "actual_value": actual_value,
            "chronos_q0.5_median": 2 * ensemble_value - 100.0,
            "random_walk_forecast": 100.0,
            "alpha": 0.5,
            "ensemble_forecast": ensemble_value,
        }
        for index in range(44)
    ])


class EvaluateH90LockedEnsembleTest(unittest.TestCase):
    def test_includes_candidate_when_both_errors_improve(self) -> None:
        _, _, _, decision = evaluate_forecast(rows(101.5))
        self.assertTrue(decision["passed_h90_service_candidate_criteria"])
        self.assertFalse(decision["alpha_was_reselected_for_h90"])

    def test_drops_candidate_when_random_walk_is_better(self) -> None:
        _, _, _, decision = evaluate_forecast(rows(99.5, actual_value=101.0))
        self.assertFalse(decision["passed_h90_service_candidate_criteria"])
        self.assertEqual(decision["next_action"], "drop_h90_service_candidate_do_not_retune_alpha")


if __name__ == "__main__":
    unittest.main()
