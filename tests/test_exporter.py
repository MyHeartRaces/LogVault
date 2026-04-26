import tempfile
import unittest
from pathlib import Path

from logvault.exporter import export_bundle


class ExporterTests(unittest.TestCase):
    def test_export_bundle_writes_summary_and_archive(self):
        report = {
            "code": "abc",
            "title": "Test Report",
            "owner": {"name": "Tester"},
            "zone": {"name": "Test Zone"},
            "fights": [
                {
                    "id": 1,
                    "name": "Boss",
                    "kill": True,
                    "startTime": 0,
                    "endTime": 120000,
                    "bossPercentage": 0,
                }
            ],
            "masterData": {"actors": [{"id": 1, "name": "Player"}], "abilities": []},
        }
        tables = {"DamageDone": {"entries": [{"name": "Player", "total": 12345, "dps": 102.4}]}}
        events = {"Deaths": iter([{"timestamp": 1000, "type": "death", "sourceID": 1}])}

        with tempfile.TemporaryDirectory() as temp:
            out_dir, archive = export_bundle(
                out_dir=Path(temp) / "bundle",
                report=report,
                fight_ids=[1],
                tables=tables,
                events_by_type=events,
                source_url="abc",
                make_zip=True,
            )

            self.assertTrue((out_dir / "summary.md").exists())
            self.assertTrue((out_dir / "tables" / "DamageDone.csv").exists())
            self.assertTrue((out_dir / "events" / "Deaths.jsonl").exists())
            self.assertIsNotNone(archive)
            self.assertTrue(archive.exists())


if __name__ == "__main__":
    unittest.main()

