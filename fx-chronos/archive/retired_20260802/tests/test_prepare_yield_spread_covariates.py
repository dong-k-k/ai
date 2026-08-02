from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.yield_spread.prepare_yield_spread_covariates import (  # noqa: E402
    build_usd_yield_spread_covariates,
)


def kr_row(date: str, value: float, safe_date: str) -> dict[str, object]:
    return {
        "date": date,
        "normalized_rate": value,
        "normalized_unit": "연%",
        "stat_code": "817Y002",
        "item_code": "010200000",
        "item_name": "국고채(3년)",
        "kr_yield_source_published_at_kst": f"{date}T16:00:00+09:00",
        "kr_yield_safe_from_krw_date": safe_date,
        "kr_yield_availability_rule": "test",
    }


def us_row(date: str, value: float | None, safe_date: str) -> dict[str, object]:
    return {
        "date": date,
        "us_treasury_3y_percent": value,
        "series_id": "DGS3",
        "unit": "Percent",
        "frequency": "Daily",
        "h15_release_date": safe_date,
        "us_yield_available_at_et": "2024-01-08T16:15:00-05:00",
        "us_yield_available_at_kst": "2024-01-09T06:15:00+09:00",
        "us_yield_safe_from_krw_date": safe_date,
        "us_yield_release_regime": "test",
        "us_yield_gap_policy": "none",
    }


class PrepareYieldSpreadCovariatesTest(unittest.TestCase):
    def test_asof_uses_latest_available_rates_and_computes_us_minus_kr(self) -> None:
        usd = pd.DataFrame(
            {"date": ["2024-01-09", "2024-01-10", "2024-01-11"], "value": [1300, 1301, 1302]}
        )
        kr = pd.DataFrame(
            [
                kr_row("2024-01-08", 3.20, "2024-01-09"),
                kr_row("2024-01-09", 3.10, "2024-01-10"),
                kr_row("2024-01-11", 3.00, "2024-01-12"),
            ]
        )
        us = pd.DataFrame(
            [
                us_row("2024-01-05", 4.40, "2024-01-10"),
                us_row("2024-01-08", 4.25, "2024-01-10"),
                us_row("2024-01-11", 4.20, "2024-01-12"),
            ]
        )

        aligned, audit = build_usd_yield_spread_covariates(usd, kr, us)

        self.assertEqual(
            aligned["date"].dt.strftime("%Y-%m-%d").tolist(),
            ["2024-01-10", "2024-01-11"],
        )
        self.assertEqual(aligned["kr_treasury_3y_percent"].tolist(), [3.10, 3.10])
        self.assertEqual(aligned["us_treasury_3y_percent"].tolist(), [4.25, 4.25])
        self.assertAlmostEqual(aligned.loc[0, "us_kr_3y_yield_spread_pct_point"], 1.15)
        self.assertTrue(audit.empty)

    def test_empty_us_value_is_audited_and_not_selected(self) -> None:
        usd = pd.DataFrame({"date": ["2024-01-10"], "value": [1300]})
        kr = pd.DataFrame(
            [
                kr_row("2024-01-09", 3.10, "2024-01-10"),
                kr_row("2024-01-10", 3.00, "2024-01-11"),
            ]
        )
        us = pd.DataFrame(
            [
                us_row("2024-01-05", 4.40, "2024-01-10"),
                us_row("2024-01-08", None, "2024-01-10"),
                us_row("2024-01-10", 4.20, "2024-01-11"),
            ]
        )

        aligned, audit = build_usd_yield_spread_covariates(usd, kr, us)

        self.assertEqual(aligned.loc[0, "us_treasury_3y_percent"], 4.40)
        self.assertEqual(
            aligned.loc[0, "us_yield_observation_date"], pd.Timestamp("2024-01-05")
        )
        self.assertEqual(audit["source"].tolist(), ["us_treasury_3y"])
        self.assertEqual(audit["exclusion_reason"].tolist(), ["empty_value"])

    def test_future_safe_date_is_not_connected(self) -> None:
        usd = pd.DataFrame({"date": ["2024-01-10"], "value": [1300]})
        kr = pd.DataFrame(
            [
                kr_row("2024-01-09", 3.10, "2024-01-11"),
                kr_row("2024-01-10", 3.00, "2024-01-11"),
            ]
        )
        us = pd.DataFrame(
            [
                us_row("2024-01-08", 4.25, "2024-01-11"),
                us_row("2024-01-10", 4.20, "2024-01-11"),
            ]
        )

        with self.assertRaisesRegex(RuntimeError, "결합 결과가 비었습니다"):
            build_usd_yield_spread_covariates(usd, kr, us)

    def test_usd_dates_after_common_yield_end_are_excluded(self) -> None:
        usd = pd.DataFrame(
            {"date": ["2024-01-10", "2024-01-11"], "value": [1300, 1301]}
        )
        kr = pd.DataFrame(
            [
                kr_row("2024-01-09", 3.20, "2024-01-10"),
                kr_row("2024-01-10", 3.10, "2024-01-11"),
            ]
        )
        us = pd.DataFrame(
            [
                us_row("2024-01-09", 4.30, "2024-01-10"),
                us_row("2024-01-10", 4.25, "2024-01-11"),
            ]
        )

        aligned, _ = build_usd_yield_spread_covariates(usd, kr, us)

        self.assertEqual(
            aligned["date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-01-10"]
        )


if __name__ == "__main__":
    unittest.main()
