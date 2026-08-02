from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.broad_usd.prepare_broad_usd_covariates import build_usd_broad_usd_covariates  # noqa: E402


def broad_row(date: str, value: float | None, safe_date: str | None) -> dict[str, object]:
    return {
        "date": date,
        "broad_usd_index": value,
        "series_id": "DTWEXBGS",
        "unit": "Index Jan 2006=100",
        "frequency": "Daily",
        "h10_release_date": safe_date,
        "available_at_et": "2024-01-08T16:15:00-05:00" if safe_date else None,
        "available_at_kst": "2024-01-09T06:15:00+09:00" if safe_date else None,
        "safe_from_krw_date": safe_date,
        "release_regime": "weekly" if safe_date else "unresolved",
        "availability_rule": "test rule",
    }


class PrepareBroadUsdCovariatesTest(unittest.TestCase):
    def test_asof_uses_latest_observation_from_available_release(self) -> None:
        usd = pd.DataFrame(
            {"date": ["2024-01-09", "2024-01-10", "2024-01-11"], "value": [1300, 1301, 1302]}
        )
        broad = pd.DataFrame(
            [
                broad_row("2024-01-02", 119.2, "2024-01-10"),
                broad_row("2024-01-05", 119.5, "2024-01-10"),
            ]
        )

        aligned, audit = build_usd_broad_usd_covariates(usd, broad)

        self.assertEqual(aligned["date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-01-10", "2024-01-11"])
        self.assertEqual(aligned["broad_usd_index"].tolist(), [119.5, 119.5])
        self.assertEqual(aligned["broad_usd_observation_date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-01-05", "2024-01-05"])
        self.assertTrue(audit.empty)

    def test_empty_latest_observation_is_excluded_not_filled(self) -> None:
        usd = pd.DataFrame({"date": ["2024-01-10"], "value": [1300]})
        broad = pd.DataFrame(
            [
                broad_row("2024-01-04", 119.4, "2024-01-10"),
                broad_row("2024-01-05", None, "2024-01-10"),
            ]
        )

        aligned, audit = build_usd_broad_usd_covariates(usd, broad)

        self.assertEqual(aligned.loc[0, "broad_usd_index"], 119.4)
        self.assertEqual(aligned.loc[0, "broad_usd_observation_date"], pd.Timestamp("2024-01-04"))
        self.assertEqual(audit["exclusion_reason"].tolist(), ["empty_value"])

    def test_unresolved_release_is_preserved_in_audit(self) -> None:
        usd = pd.DataFrame({"date": ["2024-01-10"], "value": [1300]})
        broad = pd.DataFrame(
            [
                broad_row("2008-12-31", 100.0, None),
                broad_row("2024-01-05", 119.5, "2024-01-10"),
            ]
        )

        aligned, audit = build_usd_broad_usd_covariates(usd, broad)

        self.assertEqual(len(aligned), 1)
        self.assertEqual(
            audit["exclusion_reason"].tolist(), ["release_availability_unresolved"]
        )


if __name__ == "__main__":
    unittest.main()
