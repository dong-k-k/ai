from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.broad_usd.prepare_broad_usd_availability import (  # noqa: E402
    assign_release_availability,
    parse_release_dates,
    serialize_availability,
)


class PrepareBroadUsdAvailabilityTest(unittest.TestCase):
    def test_parse_release_dates_validates_and_sorts(self) -> None:
        payload = [
            {
                "yearValue": "2024",
                "Months": [
                    {
                        "MonthName": "January",
                        "MonthValue": "202401",
                        "Dates": ["20240116", "20240108"],
                    }
                ],
            }
        ]
        dates = parse_release_dates(json.dumps(payload).encode())
        self.assertEqual(dates.strftime("%Y-%m-%d").tolist(), ["2024-01-08", "2024-01-16"])

    def test_assignment_uses_release_after_end_of_observation_week(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-08"],
                "broad_usd_index": [119.2, 119.3],
                "series_id": ["DTWEXBGS"] * 2,
                "unit": ["Index Jan 2006=100"] * 2,
                "frequency": ["Daily"] * 2,
            }
        )
        releases = pd.DatetimeIndex(pd.to_datetime(["2024-01-08", "2024-01-16"]))

        result = assign_release_availability(observations, releases)

        self.assertEqual(result["h10_release_date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-01-08", "2024-01-16"])
        self.assertEqual(result["available_at_kst"].map(lambda value: value.strftime("%Y-%m-%d %H:%M %Z")).tolist(), ["2024-01-09 06:15 KST", "2024-01-17 06:15 KST"])
        self.assertEqual(result["safe_from_krw_date"].tolist(), ["2024-01-10", "2024-01-18"])

    def test_midweek_extra_release_does_not_expose_current_week(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2024-08-05"],
                "broad_usd_index": [120.0],
                "series_id": ["DTWEXBGS"],
                "unit": ["Index Jan 2006=100"],
                "frequency": ["Daily"],
            }
        )
        releases = pd.DatetimeIndex(
            pd.to_datetime(["2024-08-05", "2024-08-07", "2024-08-12"])
        )

        result = assign_release_availability(observations, releases)

        self.assertEqual(result.loc[0, "h10_release_date"], pd.Timestamp("2024-08-12"))

    def test_serialization_preserves_time_and_utc_offsets(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2024-01-02"],
                "broad_usd_index": [119.2],
                "series_id": ["DTWEXBGS"],
                "unit": ["Index Jan 2006=100"],
                "frequency": ["Daily"],
            }
        )
        releases = pd.DatetimeIndex(pd.to_datetime(["2024-01-08"]))
        result = serialize_availability(
            assign_release_availability(observations, releases)
        )

        self.assertEqual(result.loc[0, "available_at_et"], "2024-01-08T16:15:00-05:00")
        self.assertEqual(result.loc[0, "available_at_kst"], "2024-01-09T06:15:00+09:00")

    def test_pre_2009_rows_are_preserved_without_invented_availability(self) -> None:
        observations = pd.DataFrame(
            {
                "date": ["2008-12-31", "2009-01-05"],
                "broad_usd_index": [100.0, 101.0],
                "series_id": ["DTWEXBGS"] * 2,
                "unit": ["Index Jan 2006=100"] * 2,
                "frequency": ["Daily"] * 2,
            }
        )
        releases = pd.DatetimeIndex(pd.to_datetime(["2009-01-05", "2009-01-12"]))

        result = assign_release_availability(observations, releases)

        self.assertTrue(pd.isna(result.loc[0, "h10_release_date"]))
        self.assertEqual(result.loc[0, "safe_from_krw_date"], "")
        self.assertEqual(result.loc[1, "h10_release_date"], pd.Timestamp("2009-01-12"))


if __name__ == "__main__":
    unittest.main()
