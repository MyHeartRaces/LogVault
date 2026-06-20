from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .content import int_or_none, is_mythic_plus_report, normalize_content_text
from .selection import fight_completed


MYTHIC_RAID_DIFFICULTY_ID = 5
KEYSTONE_LEVEL_FIELDS = ("keystoneLevel", "keyLevel", "mythicPlusLevel")
KEYSTONE_BONUS_FIELDS = ("keystoneBonus", "keyBonus", "mythicPlusBonus")
KEYSTONE_TIMED_FIELDS = ("timed", "inTime", "completedInTime", "keystoneCompletedInTime")
KEYSTONE_LEVEL_RE = re.compile(r"(?<!\d)\+(\d{1,2})(?!\d)")


@dataclass(frozen=True)
class MythicPlusFight:
    fight_id: int
    dungeon_key: str
    dungeon_name: str
    level: int


def essential_includes_raid(content_scope: str | None) -> bool:
    return content_scope in {None, "raid", "zone"}


def essential_includes_mythic_plus(content_scope: str | None) -> bool:
    return content_scope in {None, "mythic_plus", "zone"}


def select_mythic_raid_fight_ids(report: dict[str, Any], *, completed_only: bool = True) -> list[int]:
    selected: list[int] = []
    for fight in report.get("fights") or []:
        fight_id = int_or_none(fight.get("id"))
        if fight_id is None:
            continue
        if int_or_none(fight.get("difficulty")) != MYTHIC_RAID_DIFFICULTY_ID:
            continue
        if int_or_none(fight.get("encounterID")) is None or int_or_none(fight.get("encounterID")) <= 0:
            continue
        if completed_only and not fight_completed(fight):
            continue
        selected.append(fight_id)
    return selected


def extract_mythic_plus_fights(report: dict[str, Any], *, completed_only: bool = True) -> list[MythicPlusFight]:
    if is_mythic_plus_report(report) is not True:
        return []

    entries: list[MythicPlusFight] = []
    for fight in report.get("fights") or []:
        fight_id = int_or_none(fight.get("id"))
        if fight_id is None:
            continue
        if completed_only and not fight_completed(fight):
            continue
        if not mythic_plus_timed(fight):
            continue
        level = mythic_plus_level(fight, report)
        if level is None:
            continue
        dungeon_name = mythic_plus_dungeon_name(fight, report)
        dungeon_key = normalize_content_text(dungeon_name)
        if not dungeon_key:
            dungeon_key = str(report.get("code") or fight_id)
        entries.append(
            MythicPlusFight(
                fight_id=fight_id,
                dungeon_key=dungeon_key,
                dungeon_name=dungeon_name or dungeon_key,
                level=level,
            )
        )
    return entries


def mythic_plus_target_levels(entries: list[MythicPlusFight]) -> dict[str, set[int]]:
    best_by_dungeon: dict[str, int] = {}
    for entry in entries:
        best_by_dungeon[entry.dungeon_key] = max(entry.level, best_by_dungeon.get(entry.dungeon_key, entry.level))
    return {dungeon: {level, level - 1} for dungeon, level in best_by_dungeon.items()}


def mythic_plus_targets_summary(entries: list[MythicPlusFight], targets: dict[str, set[int]]) -> str:
    names: dict[str, str] = {}
    for entry in entries:
        names.setdefault(entry.dungeon_key, entry.dungeon_name)
    parts = []
    for dungeon_key in sorted(targets, key=lambda key: names.get(key, key)):
        levels = sorted((level for level in targets[dungeon_key] if level > 0), reverse=True)
        level_label = "/".join(f"+{level}" for level in levels)
        parts.append(f"{names.get(dungeon_key, dungeon_key)} {level_label}")
    return ", ".join(parts)


def mythic_plus_level(fight: dict[str, Any], report: dict[str, Any]) -> int | None:
    for container in (fight, report):
        for field in KEYSTONE_LEVEL_FIELDS:
            level = int_or_none(container.get(field))
            if level is not None:
                return level

    text = " ".join(
        str(value)
        for value in (
            fight.get("name"),
            report.get("title"),
            (report.get("zone") or {}).get("name"),
        )
        if value
    )
    match = KEYSTONE_LEVEL_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def mythic_plus_timed(fight: dict[str, Any]) -> bool:
    if not fight_completed(fight):
        return False
    for field in KEYSTONE_TIMED_FIELDS:
        timed = bool_or_none(fight.get(field))
        if timed is not None:
            return timed
    for field in KEYSTONE_BONUS_FIELDS:
        bonus = int_or_none(fight.get(field))
        if bonus is not None:
            return bonus > 0
    return False


def mythic_plus_dungeon_name(fight: dict[str, Any], report: dict[str, Any]) -> str:
    for value in (fight.get("name"), (report.get("zone") or {}).get("name"), report.get("title")):
        text = strip_keystone_level(str(value or "").strip())
        if text:
            return text
    return ""


def strip_keystone_level(value: str) -> str:
    stripped = KEYSTONE_LEVEL_RE.sub("", value)
    return re.sub(r"\s+", " ", stripped.replace("()", "")).strip(" -:")


def bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None
