from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from src.experiments.yield_spread.collect_h15_weekly_releases import (  # noqa: E402
    build_weekly_archive,
    find_weekly_release,
    iter_week_starts,
    parse_weekly_release_date,
)


def release_html(date_text: str) -> bytes:
    return f'<div class="dates">Release Date: {date_text}</div>'.encode()


class CollectH15WeeklyReleasesTest(unittest.TestCase):
    def test_parse_release_date(self) -> None:
        date = parse_weekly_release_date(release_html("October 26, 2015"))
        self.assertEqual(date, pd.Timestamp("2015-10-26"))

    def test_find_weekly_release_moves_to_tuesday_after_holiday(self) -> None:
        def fake_fetcher(url: str) -> bytes | None:
            if "20150119" in url:
                return None
            if "20150120" in url:
                return release_html("January 20, 2015")
            return None

        release_date, _, url = find_weekly_release(pd.Timestamp("2015-01-19"), fake_fetcher)
        self.assertEqual(release_date, pd.Timestamp("2015-01-20"))
        self.assertIn("20150120", url)

    def test_archive_url_date_may_differ_from_release_date_within_week(self) -> None:
        def fake_fetcher(url: str) -> bytes | None:
            if "20160523" in url:
                return None
            if "20160524" in url:
                return release_html("May 23, 2016")
            return None

        release_date, _, url = find_weekly_release(pd.Timestamp("2016-05-23"), fake_fetcher)
        self.assertEqual(release_date, pd.Timestamp("2016-05-23"))
        self.assertIn("20160524", url)

    def test_iter_week_starts_requires_mondays(self) -> None:
        weeks = iter_week_starts("2015-01-05", "2015-01-19")
        self.assertEqual(len(weeks), 3)
        with self.assertRaises(ValueError):
            iter_week_starts("2015-01-06", "2015-01-19")

    def test_archive_preserves_raw_release(self) -> None:
        raw = release_html("January 5, 2015")
        releases = {
            "2015-01-05": (
                pd.Timestamp("2015-01-05"),
                raw,
                "https://www.federalreserve.gov/releases/h15/20150105/",
            )
        }
        archive_bytes, manifest, dates = build_weekly_archive(releases)
        with ZipFile(BytesIO(archive_bytes)) as archive:
            self.assertEqual(archive.read("2015-01-05.html"), raw)
        self.assertEqual(len(manifest[0]["sha256"]), 64)
        self.assertEqual(dates.tolist(), [pd.Timestamp("2015-01-05")])


if __name__ == "__main__":
    unittest.main()
