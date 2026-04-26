from __future__ import annotations

import csv
import json
import re
import shutil
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def export_bundle(
    *,
    out_dir: Path,
    report: dict[str, Any],
    fight_ids: list[int],
    tables: dict[str, Any],
    events_by_type: dict[str, Iterable[dict[str, Any]]],
    source_url: str,
    make_zip: bool = True,
) -> tuple[Path, Path | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = out_dir / "tables"
    events_dir = out_dir / "events"
    tables_dir.mkdir(parents=True, exist_ok=True)
    events_dir.mkdir(parents=True, exist_ok=True)

    metadata = build_metadata(report=report, fight_ids=fight_ids, source_url=source_url)
    write_json(out_dir / "metadata.json", metadata)
    write_csv(out_dir / "fights.csv", selected_fights(report.get("fights") or [], fight_ids))
    write_csv(out_dir / "actors.csv", ((report.get("masterData") or {}).get("actors") or []))
    write_csv(out_dir / "abilities.csv", ((report.get("masterData") or {}).get("abilities") or []))

    for table_type, table_data in tables.items():
        write_json(tables_dir / f"{safe_name(table_type)}.json", table_data)
        rows = table_rows(table_data)
        if rows:
            write_csv(tables_dir / f"{safe_name(table_type)}.csv", rows)

    event_counts: dict[str, int] = {}
    for event_type, events in events_by_type.items():
        jsonl_path = events_dir / f"{safe_name(event_type)}.jsonl"
        csv_path = events_dir / f"{safe_name(event_type)}.csv"
        count = write_events(jsonl_path, csv_path, events)
        event_counts[event_type] = count

    summary = render_summary(
        report=report,
        fight_ids=fight_ids,
        source_url=source_url,
        tables=tables,
        event_counts=event_counts,
    )
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")

    archive_path: Path | None = None
    if make_zip:
        archive_path = zip_bundle(out_dir)
    return out_dir, archive_path


def build_metadata(*, report: dict[str, Any], fight_ids: list[int], source_url: str) -> dict[str, Any]:
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "sourceUrl": source_url,
        "report": {
            "code": report.get("code"),
            "title": report.get("title"),
            "owner": (report.get("owner") or {}).get("name"),
            "zone": report.get("zone"),
            "startTime": report.get("startTime"),
            "endTime": report.get("endTime"),
        },
        "selectedFightIDs": fight_ids,
        "files": {
            "summary": "summary.md",
            "metadata": "metadata.json",
            "fights": "fights.csv",
            "actors": "actors.csv",
            "abilities": "abilities.csv",
            "tables": "tables/*.json and tables/*.csv",
            "events": "events/*.jsonl and events/*.csv",
        },
    }


def render_summary(
    *,
    report: dict[str, Any],
    fight_ids: list[int],
    source_url: str,
    tables: dict[str, Any],
    event_counts: dict[str, int],
) -> str:
    title = report.get("title") or report.get("code") or "Warcraft Logs report"
    owner = (report.get("owner") or {}).get("name") or "unknown"
    zone = (report.get("zone") or {}).get("name") or "unknown"
    fights = selected_fights(report.get("fights") or [], fight_ids)
    lines = [
        f"# {title}",
        "",
        f"- Report: `{report.get('code')}`",
        f"- Source: {source_url}",
        f"- Owner: {owner}",
        f"- Zone: {zone}",
        f"- Exported: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "",
        "## Selected fights",
        "",
    ]

    if fights:
        lines.extend(markdown_table(fight_summary_rows(fights), ["id", "name", "result", "duration", "boss%"]))
    else:
        lines.append("No fights were selected.")

    lines.extend(["", "## Top tables", ""])
    for table_type, table_data in tables.items():
        entries = table_entries(table_data)[:15]
        lines.extend([f"### {table_type}", ""])
        if not entries:
            lines.extend(["No tabular entries were returned.", ""])
            continue
        rows = ranking_rows(entries)
        lines.extend(markdown_table(rows, ["#", "name", "total", "perSecond", "activeTime", "type"]))
        lines.append("")

    lines.extend(["## Event files", ""])
    if event_counts:
        lines.extend(markdown_table(
            [{"type": event_type, "events": str(count)} for event_type, count in event_counts.items()],
            ["type", "events"],
        ))
    else:
        lines.append("Event export was disabled.")

    lines.extend([
        "",
        "## How to read this bundle",
        "",
        "- `summary.md` is the quick human-readable overview.",
        "- `tables/*.csv` contains aggregate Warcraft Logs tables such as damage, healing, deaths, casts, interrupts.",
        "- `events/*.jsonl` contains one raw event per line for detailed analysis.",
        "- `events/*.csv` contains the same events with common columns plus a raw JSON column.",
    ])
    return "\n".join(lines) + "\n"


def selected_fights(fights: list[dict[str, Any]], fight_ids: list[int]) -> list[dict[str, Any]]:
    wanted = set(fight_ids)
    return [fight for fight in fights if int(fight.get("id") or -1) in wanted]


def fight_summary_rows(fights: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for fight in fights:
        start = int(fight.get("startTime") or 0)
        end = int(fight.get("endTime") or start)
        boss_percentage = fight.get("bossPercentage")
        if boss_percentage is None:
            boss = ""
        else:
            boss = f"{float(boss_percentage):.2f}%"
        rows.append(
            {
                "id": str(fight.get("id", "")),
                "name": str(fight.get("name") or "Unknown"),
                "result": "kill" if fight.get("kill") else "wipe",
                "duration": format_duration_ms(end - start),
                "boss%": boss,
            }
        )
    return rows


def ranking_rows(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, entry in enumerate(entries, start=1):
        rows.append(
            {
                "#": str(index),
                "name": str(entry.get("name") or entry.get("sourceName") or entry.get("targetName") or ""),
                "total": format_number(first_present(entry, "total", "amount", "uses", "hitCount", "count")),
                "perSecond": format_number(first_present(entry, "dps", "hps", "persecondamount", "perSecondAmount")),
                "activeTime": format_active_time(entry.get("activeTime")),
                "type": str(entry.get("type") or entry.get("icon") or entry.get("class") or ""),
            }
        )
    return rows


def table_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return list(value)
    if not isinstance(value, dict):
        return []

    for key in ("entries", "data", "auras", "rankings"):
        child = value.get(key)
        if isinstance(child, list) and all(isinstance(item, dict) for item in child):
            return list(child)

    for child in value.values():
        nested = table_entries(child)
        if nested:
            return nested
    return []


def table_rows(value: Any) -> list[dict[str, Any]]:
    rows = table_entries(value)
    if not rows and isinstance(value, dict):
        rows = [value]
    return rows


def write_events(jsonl_path: Path, csv_path: Path, events: Iterable[dict[str, Any]]) -> int:
    count = 0
    fieldnames = ["timestamp", "type", "sourceID", "targetID", "abilityGameID", "ability", "amount", "hitType", "raw"]
    with jsonl_path.open("w", encoding="utf-8") as jsonl, csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for event in events:
            count += 1
            jsonl.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            jsonl.write("\n")
            writer.writerow({key: normalize_csv_value(value) for key, value in event_common_row(event).items()})
    return count


def event_common_row(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": event.get("timestamp"),
        "type": event.get("type"),
        "sourceID": event.get("sourceID"),
        "targetID": event.get("targetID"),
        "abilityGameID": event.get("abilityGameID"),
        "ability": event.get("ability"),
        "amount": event.get("amount"),
        "hitType": event.get("hitType"),
        "raw": json.dumps(event, ensure_ascii=False, sort_keys=True),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    materialized = list(rows)
    fieldnames = sorted({key for row in materialized for key in row.keys()})
    if not fieldnames:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in materialized:
            writer.writerow({key: normalize_csv_value(value) for key, value in row.items()})


def zip_bundle(out_dir: Path) -> Path:
    archive = out_dir.with_suffix(".zip")
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                zip_file.write(path, path.relative_to(out_dir.parent))
    return archive


def fresh_output_dir(base_dir: Path, report_code: str, title: str | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = safe_name(title or report_code)[:48].strip("-") or report_code
    path = base_dir / f"{report_code}-{suffix}-{stamp}"
    if path.exists():
        shutil.rmtree(path)
    return path


def markdown_table(rows: list[dict[str, str]], columns: list[str]) -> list[str]:
    if not rows:
        return []
    escaped_rows = [{column: escape_markdown(str(row.get(column, ""))) for column in columns} for row in rows]
    output = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in escaped_rows:
        output.append("| " + " | ".join(row[column] for column in columns) + " |")
    return output


def escape_markdown(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def normalize_csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def first_present(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def format_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return f"{int(number):,}".replace(",", " ")
    return f"{number:,.1f}".replace(",", " ")


def format_active_time(value: Any) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number <= 1:
        return f"{number * 100:.1f}%"
    return f"{number:.1f}"


def format_duration_ms(value: int | float) -> str:
    seconds = max(0, int(value // 1000))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:d}:{seconds:02d}"


def safe_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    name = re.sub(r"-+", "-", name).strip("-._")
    return name or "export"
