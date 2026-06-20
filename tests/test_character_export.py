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

    def test_scan_skips_empty_report_with_last_selector(self):
        reports = {
            "empty": {
                "code": "empty",
                "title": "Empty",
                "zone": {"name": "Sporefall"},
                "fights": [],
            },
        }
        options = CharacterReportsOptions(
            character_name="Player",
            server_slug="realm",
            server_region="eu",
            completed_only=True,
            fight="last",
        )

        with tempfile.TemporaryDirectory() as temp:
            planned, skipped = scan_exportable_reports(
                client=FakeClient(reports),
                options=options,
                source_reports=[{"code": "empty"}],
                reports_dir=Path(temp),
                progress=lambda _message: None,
            )

        self.assertEqual(planned, [])
        self.assertEqual(skipped[0]["code"], "empty")
        self.assertEqual(skipped[0]["reason"], "No completed fights selected.")

    def test_essential_scan_keeps_mplus_targets_and_mythic_raid(self):
        reports = {
            "ak18": {
                "code": "ak18",
                "title": "Ara-Kara +18",
                "zone": {"name": "Ara-Kara"},
                "fights": [
                    {
                        "id": 1,
                        "name": "Ara-Kara",
                        "difficulty": 10,
                        "kill": True,
                        "keystoneLevel": 18,
                        "keystoneBonus": 1,
                    }
                ],
            },
            "ak17": {
                "code": "ak17",
                "title": "Ara-Kara +17",
                "zone": {"name": "Ara-Kara"},
                "fights": [
                    {
                        "id": 2,
                        "name": "Ara-Kara",
                        "difficulty": 10,
                        "kill": True,
                        "keystoneLevel": 17,
                        "keystoneBonus": 1,
                    }
                ],
            },
            "ak16": {
                "code": "ak16",
                "title": "Ara-Kara +16",
                "zone": {"name": "Ara-Kara"},
                "fights": [
                    {
                        "id": 3,
                        "name": "Ara-Kara",
                        "difficulty": 10,
                        "kill": True,
                        "keystoneLevel": 16,
                        "keystoneBonus": 1,
                    }
                ],
            },
            "raid": {
                "code": "raid",
                "title": "Raid",
                "zone": {"name": "Sporefall"},
                "fights": [
                    {"id": 4, "encounterID": 100, "name": "Boss", "difficulty": 5, "kill": True},
                    {"id": 5, "encounterID": 200, "name": "Heroic Boss", "difficulty": 4, "kill": True},
                ],
            },
        }
        options = CharacterReportsOptions(
            character_name="Player",
            server_slug="realm",
            server_region="eu",
            essential_mode=True,
            fight="last",
        )

        with tempfile.TemporaryDirectory() as temp:
            planned, skipped = scan_exportable_reports(
                client=FakeClient(reports),
                options=options,
                source_reports=[{"code": "ak18"}, {"code": "ak17"}, {"code": "ak16"}, {"code": "raid"}],
                reports_dir=Path(temp),
                progress=lambda _message: None,
            )

        self.assertEqual([item.metadata["code"] for item in planned], ["ak18", "ak17", "raid"])
        self.assertEqual([item.fight_ids for item in planned], [[1], [2], [4]])
        self.assertEqual(skipped[-1]["code"], "ak16")
        self.assertEqual(skipped[-1]["reason"], "essential Mythic+ level filter")


if __name__ == "__main__":
    unittest.main()
