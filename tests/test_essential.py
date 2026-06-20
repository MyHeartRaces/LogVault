import unittest

from logvault.essential import (
    extract_mythic_plus_fights,
    mythic_plus_target_levels,
    select_mythic_raid_fight_ids,
    strip_keystone_level,
)


class EssentialTests(unittest.TestCase):
    def test_mythic_plus_targets_keep_best_and_previous_per_dungeon(self):
        reports = [
            {
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
            {
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
                        "keystoneBonus": 2,
                    }
                ],
            },
            {
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
        ]
        entries = [entry for report in reports for entry in extract_mythic_plus_fights(report)]
        targets = mythic_plus_target_levels(entries)

        allowed = [
            entry.fight_id
            for entry in entries
            if entry.level in targets.get(entry.dungeon_key, set())
        ]

        self.assertEqual(allowed, [1, 2])

    def test_mythic_plus_requires_timed_completion(self):
        report = {
            "code": "depleted",
            "title": "Ara-Kara +18",
            "zone": {"name": "Ara-Kara"},
            "fights": [
                {
                    "id": 1,
                    "name": "Ara-Kara",
                    "difficulty": 10,
                    "kill": True,
                    "keystoneLevel": 18,
                    "keystoneBonus": 0,
                }
            ],
        }

        self.assertEqual(extract_mythic_plus_fights(report), [])

    def test_dungeon_name_strips_keystone_level(self):
        self.assertEqual(strip_keystone_level("Ara-Kara +18"), "Ara-Kara")

    def test_raid_selection_keeps_only_completed_mythic_bosses(self):
        report = {
            "code": "raid",
            "title": "Raid night",
            "zone": {"name": "Sporefall"},
            "fights": [
                {"id": 1, "encounterID": 100, "difficulty": 5, "kill": True},
                {"id": 2, "encounterID": 200, "difficulty": 5, "kill": False},
                {"id": 3, "encounterID": 300, "difficulty": 4, "kill": True},
                {"id": 4, "encounterID": 0, "difficulty": 5, "kill": True},
            ],
        }

        self.assertEqual(select_mythic_raid_fight_ids(report), [1])


if __name__ == "__main__":
    unittest.main()
