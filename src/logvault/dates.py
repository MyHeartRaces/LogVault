from __future__ import annotations

from datetime import UTC, datetime, time


def parse_date_bound(value: str | None, *, end: bool = False) -> float | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    try:
        if "T" in raw or " " in raw:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            parsed_date = datetime.strptime(raw, "%Y-%m-%d").date()
            parsed = datetime.combine(parsed_date, time.max if end else time.min)
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}. Use YYYY-MM-DD.") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def report_timestamp_seconds(value: int | float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number > 10_000_000_000:
        return number / 1000
    return number

