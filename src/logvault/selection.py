from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Any


REPORT_CODE_RE = re.compile(r"^[A-Za-z0-9]+$")


@dataclass(frozen=True)
class ReportInput:
    code: str
    fight_hint: str | None = None


def parse_report_input(value: str) -> ReportInput:
    """Parse a raw report code or a Warcraft Logs report URL."""
    value = value.strip()
    if REPORT_CODE_RE.fullmatch(value):
        return ReportInput(code=value)

    parsed = urllib.parse.urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    try:
        report_index = parts.index("reports")
        code = parts[report_index + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Cannot find report code in: {value}") from exc

    params: dict[str, list[str]] = {}
    params.update(urllib.parse.parse_qs(parsed.query))
    if parsed.fragment:
        params.update(urllib.parse.parse_qs(parsed.fragment))
    fight_hint = first(params.get("fight"))
    return ReportInput(code=code, fight_hint=fight_hint)


def parse_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def resolve_fight_ids(
    fights: list[dict[str, Any]],
    *,
    explicit: str | None = None,
    url_hint: str | None = None,
    include_trash: bool = False,
) -> list[int]:
    """Resolve fight selectors into concrete Warcraft Logs fight IDs."""
    selector = explicit or url_hint
    if selector:
        return resolve_selector(fights, selector)

    selected = fights if include_trash else [fight for fight in fights if int(fight.get("encounterID") or 0) > 0]
    return [int(fight["id"]) for fight in selected if fight.get("id") is not None]


def resolve_selector(fights: list[dict[str, Any]], selector: str) -> list[int]:
    normalized = selector.strip().lower()
    ids = [int(fight["id"]) for fight in fights if fight.get("id") is not None]

    if normalized in {"all", "*"}:
        return ids
    if normalized in {"boss", "bosses"}:
        return [
            int(fight["id"])
            for fight in fights
            if fight.get("id") is not None and int(fight.get("encounterID") or 0) > 0
        ]
    if normalized == "last":
        boss_ids = [
            int(fight["id"])
            for fight in fights
            if fight.get("id") is not None and int(fight.get("encounterID") or 0) > 0
        ]
        return [boss_ids[-1] if boss_ids else ids[-1]]

    resolved: list[int] = []
    for part in parse_list(selector):
        if not part.isdigit():
            raise ValueError(f"Unsupported fight selector {part!r}. Use numbers, all, boss, or last.")
        fight_id = int(part)
        if fight_id not in ids:
            raise ValueError(f"Fight {fight_id} is not present in this report.")
        resolved.append(fight_id)
    return resolved


def selected_time_window(
    fights: list[dict[str, Any]],
    fight_ids: list[int],
) -> tuple[int | None, int | None]:
    if not fight_ids:
        return None, None
    selected = [fight for fight in fights if int(fight.get("id") or -1) in fight_ids]
    starts = [int(fight["startTime"]) for fight in selected if fight.get("startTime") is not None]
    ends = [int(fight["endTime"]) for fight in selected if fight.get("endTime") is not None]
    if not starts or not ends:
        return None, None
    return min(starts), max(ends)


def first(values: list[str] | None) -> str | None:
    if not values:
        return None
    return values[0]

