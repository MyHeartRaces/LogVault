import unittest

from logvault.selection import filter_fights_by_encounter, parse_report_input, resolve_fight_ids, selected_time_window


class SelectionTests(unittest.TestCase):
    def test_parse_raw_code(self):
        parsed = parse_report_input("abc123XYZ")

        self.assertEqual(parsed.code, "abc123XYZ")
        self.assertIsNone(parsed.fight_hint)

    def test_parse_report_url_with_fragment_fight(self):
        parsed = parse_report_input("https://www.warcraftlogs.com/reports/abc123XYZ#fight=12&type=damage-done")

        self.assertEqual(parsed.code, "abc123XYZ")
        self.assertEqual(parsed.fight_hint, "12")

    def test_resolve_last_prefers_last_boss(self):
        fights = [
            {"id": 1, "encounterID": 0},
            {"id": 2, "encounterID": 100},
            {"id": 3, "encounterID": 200},
        ]

        self.assertEqual(resolve_fight_ids(fights, explicit="last"), [3])

    def test_default_selects_boss_fights(self):
        fights = [
            {"id": 1, "encounterID": 0},
            {"id": 2, "encounterID": 100},
        ]

        self.assertEqual(resolve_fight_ids(fights), [2])

    def test_filter_fights_by_encounter_id_or_name(self):
        fights = [
            {"id": 1, "encounterID": 100, "name": "The Stone Guard"},
            {"id": 2, "encounterID": 200, "name": "Feng the Accursed"},
            {"id": 3, "encounterID": 200, "name": "Feng the Accursed"},
        ]

        self.assertEqual([fight["id"] for fight in filter_fights_by_encounter(fights, "200")], [2, 3])
        self.assertEqual([fight["id"] for fight in filter_fights_by_encounter(fights, "feng")], [2, 3])

    def test_selected_time_window(self):
        fights = [
            {"id": 1, "startTime": 10, "endTime": 20},
            {"id": 2, "startTime": 30, "endTime": 50},
            {"id": 3, "startTime": 5, "endTime": 70},
        ]

        self.assertEqual(selected_time_window(fights, [1, 2]), (10, 50))


if __name__ == "__main__":
    unittest.main()
