from __future__ import annotations


DIFFICULTY_IDS = {
    "lfr": 1,
    "normal": 3,
    "heroic": 4,
    "mythic": 5,
}

DIFFICULTY_LABELS = {
    1: "LFR",
    3: "Normal",
    4: "Heroic",
    5: "Mythic",
}

DIFFICULTY_CHOICES = ["All", "Mythic", "Heroic", "Normal", "LFR"]
DIFFICULTY_SCOPE_CHOICES = ["All", "Mythic", "Heroic", "Mythic + Heroic", "Normal", "LFR"]


def parse_difficulty(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "all", "any", "все"}:
        return None
    if normalized.isdigit():
        number = int(normalized)
        if number in DIFFICULTY_LABELS:
            return number
    if normalized not in DIFFICULTY_IDS:
        choices = ", ".join(DIFFICULTY_CHOICES)
        raise ValueError(f"Unsupported difficulty {value!r}. Use one of: {choices}.")
    return DIFFICULTY_IDS[normalized]


def parse_difficulty_scope(value: str | None) -> tuple[int, ...] | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"", "all", "any", "все"}:
        return None

    for separator in ("+", "/", ";"):
        normalized = normalized.replace(separator, ",")
    normalized = normalized.replace(" and ", ",")

    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    if any(part in {"all", "any", "все"} for part in parts):
        raise ValueError("Use 'All' by itself, or list specific difficulties.")

    values: list[int] = []
    for part in parts:
        parsed = parse_difficulty(part)
        if parsed not in values:
            values.append(parsed)
    return tuple(values) or None


def difficulty_label(value: int | None) -> str:
    if value is None:
        return "All"
    return DIFFICULTY_LABELS.get(value, str(value))


def difficulty_scope_label(values: tuple[int, ...] | list[int] | None) -> str:
    if not values:
        return "All"
    return " + ".join(difficulty_label(value) for value in values)
