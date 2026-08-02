from __future__ import annotations

import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.data.collect_fred import (  # noqa: E402
    build_fred_graph_url,
    process_broad_usd_csv,
    process_dgs3_csv,
)


class CollectFredTest(unittest.TestCase):
    def test_build_url_contains_series_and_period(self) -> None:
        url = build_fred_graph_url("DTWEXBGS", "2024-01-01", "2024-03-31")
        self.assertIn("id=DTWEXBGS", url)
        self.assertIn("cosd=2024-01-01", url)
        self.assertIn("coed=2024-03-31", url)

    def test_process_preserves_empty_holiday_row(self) -> None:
        raw = (
            b"observation_date,DTWEXBGS\n"
            b"2024-01-02,119.2686\n"
            b"2024-01-03,\n"
            b"2024-01-04,119.6208\n"
        )

        processed, summary = process_broad_usd_csv(raw, "2024-01-01", "2024-03-31")

        self.assertEqual(len(processed), 3)
        self.assertTrue(processed.loc[1, "broad_usd_index"] != processed.loc[1, "broad_usd_index"])
        self.assertEqual(summary["empty_value_rows"], 1)
        self.assertEqual(summary["numeric_conversion_failures"], 0)
        self.assertTrue(summary["dates_monotonic_increasing"])

    def test_process_rejects_duplicate_dates(self) -> None:
        raw = (
            b"observation_date,DTWEXBGS\n"
            b"2024-01-02,119.2686\n"
            b"2024-01-02,119.3000\n"
        )
        with self.assertRaises(RuntimeError):
            process_broad_usd_csv(raw, "2024-01-01", "2024-03-31")

    def test_process_rejects_non_numeric_nonempty_value(self) -> None:
        raw = b"observation_date,DTWEXBGS\n2024-01-02,not-a-number\n"
        with self.assertRaises(RuntimeError):
            process_broad_usd_csv(raw, "2024-01-01", "2024-03-31")

    def test_process_dgs3_uses_rate_columns_and_preserves_holiday(self) -> None:
        raw = (
            b"observation_date,DGS3\n"
            b"2024-07-01,4.47\n"
            b"2024-07-04,\n"
            b"2024-07-05,4.31\n"
        )

        processed, summary = process_dgs3_csv(raw, "2024-07-01", "2024-07-10")

        self.assertEqual(processed.columns.tolist(), [
            "date", "us_treasury_3y_percent", "series_id", "unit", "frequency"
        ])
        self.assertEqual(processed["series_id"].unique().tolist(), ["DGS3"])
        self.assertEqual(processed["unit"].unique().tolist(), ["Percent"])
        self.assertEqual(summary["empty_value_rows"], 1)
        self.assertTrue(summary["dates_monotonic_increasing"])


if __name__ == "__main__":
    unittest.main()
