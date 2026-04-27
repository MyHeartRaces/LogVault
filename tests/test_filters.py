import unittest

from logvault.dates import parse_date_bound, report_timestamp_seconds
from logvault.difficulty import difficulty_label, parse_difficulty


class FilterTests(unittest.TestCase):
    def test_parse_difficulty(self):
        self.assertIsNone(parse_difficulty("all"))
        self.assertEqual(parse_difficulty("Mythic"), 5)
        self.assertEqual(parse_difficulty("heroic"), 4)
        self.assertEqual(parse_difficulty("3"), 3)
        self.assertEqual(difficulty_label(1), "LFR")

    def test_parse_date_bound(self):
        start = parse_date_bound("2026-01-02")
        end = parse_date_bound("2026-01-02", end=True)

        self.assertLess(start, end)

    def test_report_timestamp_seconds_accepts_ms(self):
        self.assertEqual(report_timestamp_seconds(1_700_000_000_000), 1_700_000_000)


if __name__ == "__main__":
    unittest.main()

