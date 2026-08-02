from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.jpy.prepare_covariates import build_usd_jpy_covariates  # noqa: E402


class PrepareCovariatesTest(unittest.TestCase):
    def test_aligns_dates_and_uses_only_previous_jpy_observation(self) -> None:
        usd = pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-02", "2026-07-03"],
                "value": [1350.0, 1355.0, 1360.0],
            }
        )
        jpy = pd.DataFrame(
            {
                "date": ["2026-07-01", "2026-07-03"],
                "value": [9.1, 9.3],
            }
        )

        result = build_usd_jpy_covariates(usd, jpy)

        self.assertEqual(result["date"].dt.strftime("%Y-%m-%d").tolist(), ["2026-07-03"])
        self.assertEqual(result["jpy_krw_krw_per_jpy_lag1"].tolist(), [9.1])
        self.assertEqual(
            result["jpy_source_date_lag1"].dt.strftime("%Y-%m-%d").tolist(),
            ["2026-07-01"],
        )
        self.assertEqual(result["jpy_krw_same_date_audit_only"].tolist(), [9.3])

    def test_rejects_duplicate_dates(self) -> None:
        usd = pd.DataFrame(
            {"date": ["2026-07-01", "2026-07-01"], "value": [1350.0, 1351.0]}
        )
        jpy = pd.DataFrame({"date": ["2026-07-01"], "value": [9.1]})

        with self.assertRaisesRegex(RuntimeError, "중복 날짜"):
            build_usd_jpy_covariates(usd, jpy)

    def test_rejects_weekend_observation(self) -> None:
        usd = pd.DataFrame({"date": ["2026-07-04"], "value": [1350.0]})
        jpy = pd.DataFrame({"date": ["2026-07-04"], "value": [9.1]})

        with self.assertRaisesRegex(RuntimeError, "주말 관측"):
            build_usd_jpy_covariates(usd, jpy)


if __name__ == "__main__":
    unittest.main()
