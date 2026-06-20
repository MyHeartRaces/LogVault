import unittest

from logvault.content import parse_content_scope, report_matches_content


class ContentTests(unittest.TestCase):
    def test_parse_content_scope(self):
        self.assertIsNone(parse_content_scope("All"))
        self.assertEqual(parse_content_scope("Mythic+"), "mythic_plus")
        self.assertEqual(parse_content_scope("Custom zone/tier"), "zone")

    def test_report_matches_mythic_plus_by_title(self):
        report = {"title": "Mythic+ Season 1", "zone": {"name": "Ara-Kara"}}

        self.assertTrue(report_matches_content(report, content_scope="mythic_plus"))
        self.assertFalse(report_matches_content(report, content_scope="raid"))

    def test_report_matches_custom_zone(self):
        report = {"title": "Farm", "zone": {"id": 42, "name": "Sporefall"}}

        self.assertTrue(report_matches_content(report, content_scope="zone", zone_filter="spore"))
        self.assertTrue(report_matches_content(report, content_scope="zone", zone_filter="42"))
        self.assertFalse(report_matches_content(report, content_scope="zone", zone_filter="Other"))


if __name__ == "__main__":
    unittest.main()
