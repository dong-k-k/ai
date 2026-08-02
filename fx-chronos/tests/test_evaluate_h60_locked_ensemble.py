from __future__ import annotations

import unittest

import pandas as pd

from src.evaluation.evaluate_h60_locked_ensemble import evaluate_forecast


def rows(ensemble_value: float, actual_value: float = 102.0) -> pd.DataFrame:
    records = []
    for index in range(46):
        records.append({
            "requested_origin": f"origin-{index:02d}",
            "forecast_step": 1,
            "forecast_origin_value": 100.0,
            "actual_value": actual_value,
            "chronos_q0.5_median": 2 * ensemble_value - 100.0,
            "random_walk_forecast": 100.0,
            "alpha": 0.5,
            "ensemble_forecast": ensemble_value,
        })
    return pd.DataFrame(records)


class EvaluateH60LockedEnsembleTest(unittest.TestCase):
    def test_passes_only_when_all_locked_checks_pass(self) -> None:
        criteria = {
            "minimum_origin_mae_wins_vs_random_walk": 24,
            "minimum_origin_rmse_wins_vs_random_walk": 24,
        }
        _, _, _, decision = evaluate_forecast(rows(101.5), criteria)
        self.assertTrue(decision["passed_h60_service_candidate_criteria"])
        self.assertFalse(decision["alpha_was_reselected_for_h60"])
        self.assertFalse(decision["final_test_2022_2025_used"])

    def test_fails_when_random_walk_is_better(self) -> None:
        criteria = {
            "minimum_origin_mae_wins_vs_random_walk": 24,
            "minimum_origin_rmse_wins_vs_random_walk": 24,
        }
        _, _, _, decision = evaluate_forecast(rows(99.5, actual_value=101.0), criteria)
        self.assertFalse(decision["passed_h60_service_candidate_criteria"])
        self.assertEqual(decision["next_action"], "drop_h60_service_candidate_do_not_retune_alpha")


if __name__ == "__main__":
    unittest.main()
