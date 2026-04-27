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


def difficulty_label(value: int | None) -> str:
    if value is None:
        return "All"
    return DIFFICULTY_LABELS.get(value, str(value))

