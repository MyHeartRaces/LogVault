import tempfile
import unittest
from pathlib import Path

from logvault.character_export import CharacterReportsOptions, scan_exportable_reports


class FakeClient:
    def __init__(self, reports):
        self.reports = reports

    def fetch_report_metadata(self, code, *, allow_unlisted=True):
        return self.reports[code]


class CharacterExportTests(unittest.TestCase):
    def test_scan_counts_only_completed_reports(self):
        reports = {
            "kill": {
                "code": "kill",
                "title": "Kill",
                "zone": {"name": "Sporefall"},
                "fights": [{"id": 1, "encounterID": 100, "name": "Boss", "difficulty": 5, "kill": True}],
            },
            "wipe": {
                "code": "wipe",
                "title": "Wipe",
                "zone": {"name": "Sporefall"},
                "fights": [{"id": 1, "encounterID": 100, "name": "Boss", "difficulty": 5, "kill": False}],
            },
        }
        options = CharacterReportsOptions(
            character_name="Player",
            server_slug="realm",
            server_region="eu",
            completed_only=True,
        )

        with tempfile.TemporaryDirectory() as temp:
            planned, skipped = scan_exportable_reports(
                client=FakeClient(reports),
                options=options,
                source_reports=[{"code": "kill"}, {"code": "wipe"}],
                reports_dir=Path(temp),
                progress=lambda _message: None,
            )

        self.assertEqual([item.metadata["code"] for item in planned], ["kill"])
        self.assertEqual(skipped[0]["code"], "wipe")


if __name__ == "__main__":
    unittest.main()
