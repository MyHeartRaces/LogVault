from __future__ import annotations

import re
from typing import Any


CONTENT_SCOPE_CHOICES = ["All", "Raids", "Mythic+", "Custom zone/tier"]

CONTENT_SCOPE_IDS = {
    "": None,
    "all": None,
    "any": None,
    "everything": None,
    "raid": "raid",
    "raids": "raid",
    "рейд": "raid",
    "рейды": "raid",
    "mythic+": "mythic_plus",
    "mythic plus": "mythic_plus",
    "mythic-plus": "mythic_plus",
    "m+": "mythic_plus",
    "keystone": "mythic_plus",
    "custom": "zone",
    "custom zone": "zone",
    "custom zone/tier": "zone",
    "zone": "zone",
    "tier": "zone",
}

MYTHIC_PLUS_DIFFICULTIES = {8, 10}
MYTHIC_PLUS_MARKERS = ("mythic+", "mythic plus", "m+", "keystone")


def parse_content_scope(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_content_text(value)
    if normalized not in CONTENT_SCOPE_IDS:
        choices = ", ".join(CONTENT_SCOPE_CHOICES)
        raise ValueError(f"Unsupported game mode {value!r}. Use one of: {choices}.")
    return CONTENT_SCOPE_IDS[normalized]


def content_scope_label(scope: str | None) -> str:
    if not scope:
        return "All"
    if scope == "raid":
        return "Raids"
    if scope == "mythic_plus":
        return "Mythic+"
    if scope == "zone":
        return "Custom zone/tier"
    return scope


def report_matches_content(
    report: dict[str, Any],
    *,
    content_scope: str | None,
    zone_filter: str | None = None,
    allow_unknown: bool = False,
) -> bool:
    if zone_filter and not report_matches_zone(report, zone_filter):
        return False

    if not content_scope or content_scope == "zone":
        return True
    if content_scope == "mythic_plus":
        detected = is_mythic_plus_report(report)
        return allow_unknown if detected is None else detected
    if content_scope == "raid":
        detected = is_mythic_plus_report(report)
        if detected is None:
            return allow_unknown or has_boss_fights(report)
        return not detected and (allow_unknown or has_boss_fights(report))
    return True


def validate_content_filters(content_scope: str | None, zone_filter: str | None) -> None:
    if content_scope == "zone" and not (zone_filter or "").strip():
        raise ValueError("Custom zone/tier game mode requires Zone/Tier.")


def report_matches_zone(report: dict[str, Any], zone_filter: str) -> bool:
    selector = zone_filter.strip()
    if not selector:
        return True
    zone = report.get("zone") or {}
    if selector.isdigit() and int_or_none(zone.get("id")) == int(selector):
        return True

    normalized = normalize_content_text(selector)
    haystack = " ".join(
        normalize_content_text(str(value))
        for value in (
            zone.get("name"),
            zone.get("id"),
            report.get("title"),
            report.get("code"),
        )
        if value is not None
    )
    return normalized in haystack


def is_mythic_plus_report(report: dict[str, Any]) -> bool | None:
    text = normalize_content_text(
        " ".join(
            str(value)
            for value in (
                report.get("title"),
                report.get("code"),
                (report.get("zone") or {}).get("name"),
            )
            if value
        )
    )
    if any(marker in text for marker in MYTHIC_PLUS_MARKERS):
        return True

    fights = list(report.get("fights") or [])
    if not fights:
        return None

    difficulties = {
        int(fight.get("difficulty") or -1)
        for fight in fights
        if fight.get("difficulty") is not None
    }
    if difficulties & MYTHIC_PLUS_DIFFICULTIES:
        return True
    return False


def has_boss_fights(report: dict[str, Any]) -> bool:
    return any(int(fight.get("encounterID") or 0) > 0 for fight in report.get("fights") or [])


def normalize_content_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
