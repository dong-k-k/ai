from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.yield_spread.evaluate_yield_spread_validation import (  # noqa: E402
    evaluate_forecast,
    load_settings,
)


def validation_rows(covariate_value: float, actual_value: float = 102.0) -> pd.DataFrame:
    rows = []
    for origin_index in range(48):
        rows.append(
            {
                "requested_origin": f"origin-{origin_index:02d}",
                "target_date": pd.Timestamp("2020-01-01"),
                "forecast_step": 1,
                "forecast_origin_value": 100.0,
                "actual_value": actual_value,
                "covariate_q0.1_lower": covariate_value - 1.0,
                "covariate_q0.5_median": covariate_value,
                "covariate_q0.9_upper": covariate_value + 1.0,
                "univariate_q0.5_median": 101.0,
                "random_walk_forecast": 100.0,
                "maximum_kr_yield_age_calendar_days": 11,
                "maximum_us_yield_age_calendar_days": 103,
            }
        )
    return pd.DataFrame(rows)


class EvaluateYieldSpreadValidationTest(unittest.TestCase):
    def test_candidate_passes_only_when_all_locked_checks_pass(self) -> None:
        criteria = {
            "minimum_origin_mae_wins_vs_univariate": 25,
            "minimum_origin_rmse_wins_vs_univariate": 25,
        }

        summary, _, _, _, decision = evaluate_forecast(
            validation_rows(101.9), criteria
        )

        self.assertTrue(decision["passed_candidate_entry_criteria"])
        self.assertFalse(decision["final_test_2022_2025_used"])
        self.assertEqual(summary.loc[0, "maximum_us_yield_age_calendar_days"], 103)

    def test_candidate_fails_when_random_walk_is_better(self) -> None:
        criteria = {
            "minimum_origin_mae_wins_vs_univariate": 25,
            "minimum_origin_rmse_wins_vs_univariate": 25,
        }

        _, _, _, _, decision = evaluate_forecast(
            validation_rows(101.0, actual_value=100.0), criteria
        )

        self.assertFalse(decision["passed_candidate_entry_criteria"])
        self.assertFalse(decision["criteria_checks"]["lower_mae_than_random_walk"])

    def test_load_settings_rejects_changed_snapshot_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "configs"
            config_dir.mkdir()
            data_path = root / "data.csv"
            reference_path = root / "reference.csv"
            data_path.write_text("original", encoding="utf-8")
            reference_path.write_text("reference", encoding="utf-8")
            config = {
                "model_id": "amazon/chronos-2",
                "future_covariates": [],
                "input_snapshot": {
                    "path": "data.csv",
                    "sha256": hashlib.sha256(b"different").hexdigest(),
                },
                "univariate_reference_snapshot": {
                    "path": "reference.csv",
                    "sha256": hashlib.sha256(b"reference").hexdigest(),
                },
                "validation": {
                    "expected_origins": 48,
                    "expected_rows": 960,
                    "context_length": 756,
                    "prediction_length": 20,
                    "device": "mps",
                    "batch_size": 8,
                    "cross_learning": False,
                },
                "candidate_entry_criteria": {},
            }
            config_path = config_dir / "validation.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                load_settings(config_path)


if __name__ == "__main__":
    unittest.main()
