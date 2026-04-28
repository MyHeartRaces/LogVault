from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .api import WarcraftLogsClient
from .cli_defaults import DEFAULT_EVENT_TYPES, DEFAULT_TABLE_TYPES, ESSENTIAL_EVENT_TYPES, FULL_EVENT_TYPES
from .difficulty import difficulty_scope_label
from .env import load_env_file
from .errors import DownloadCancelled
from .exporter import export_bundle, fresh_output_dir
from .selection import filter_fights_by_encounter, parse_list, parse_report_input, resolve_fight_ids, selected_time_window


ProgressCallback = Callable[[str], None]


@dataclass
class DownloadOptions:
    report: str
    fight: str | None = None
    include_trash: bool = False
    tables: str = "standard"
    events: str = "compact"
    filter_expression: str | None = None
    out: Path = Path("exports")
    make_zip: bool = True
    archive_only: bool = False
    limit: int = 10_000
    max_pages: int | None = None
    allow_unlisted: bool = True
    client_id: str | None = None
    client_secret: str | None = None
    access_token: str | None = None
    timeout: float = 60.0
    env_file: Path | None = Path(".env")
    difficulty_id: int | None = None
    difficulty_ids: tuple[int, ...] | None = None
    encounter: str | None = None
    cancel_check: Callable[[], bool] | None = None


@dataclass
class DownloadResult:
    out_dir: Path
    archive: Path | None
    report_code: str
    fight_ids: list[int]


def download_report(options: DownloadOptions, progress: ProgressCallback | None = None) -> DownloadResult:
    progress = progress or (lambda _message: None)
    if options.archive_only and not options.make_zip:
        raise ValueError("Archive-only output requires zip archive creation.")
    if options.env_file is not None:
        load_env_file(options.env_file)
    raise_if_cancelled(options.cancel_check)

    report_input = parse_report_input(options.report)
    client = WarcraftLogsClient(
        client_id=options.client_id or getenv_any("WCL_CLIENT_ID", "WARCRAFTLOGS_CLIENT_ID"),
        client_secret=options.client_secret or getenv_any("WCL_CLIENT_SECRET", "WARCRAFTLOGS_CLIENT_SECRET"),
        access_token=options.access_token or getenv_any("WCL_ACCESS_TOKEN", "WARCRAFTLOGS_ACCESS_TOKEN"),
        timeout=options.timeout,
        retry_callback=progress,
        cancel_check=options.cancel_check,
    )

    progress("Authenticating with Warcraft Logs...")
    progress(f"Fetching report metadata for {report_input.code}...")
    report = client.fetch_report_metadata(report_input.code, allow_unlisted=options.allow_unlisted)
    raise_if_cancelled(options.cancel_check)
    fights = list(report.get("fights") or [])
    difficulty_ids = option_difficulty_ids(options.difficulty_id, options.difficulty_ids)
    if difficulty_ids is not None:
        difficulty_set = set(difficulty_ids)
        fights = [fight for fight in fights if int(fight.get("difficulty") or -1) in difficulty_set]
        progress(f"Applied difficulty filter: {difficulty_scope_label(difficulty_ids)}")
    if options.encounter:
        fights = filter_fights_by_encounter(fights, options.encounter)
        progress(f"Applied encounter filter: {options.encounter}")
    fight_ids = resolve_fight_ids(
        fights,
        explicit=options.fight,
        url_hint=report_input.fight_hint,
        include_trash=options.include_trash,
    )
    if not fight_ids:
        raise ValueError("No fights selected. Use fight selector 'all' if this report has no boss pulls.")
    start_time, end_time = selected_time_window(fights, fight_ids)

    table_types = resolve_type_list(options.tables, DEFAULT_TABLE_TYPES)
    event_types = resolve_event_type_list(options.events)
    progress(
        f"Selected fights: {', '.join(str(fight_id) for fight_id in fight_ids)}; "
        f"tables: {len(table_types)}; event streams: {len(event_types)}"
    )

    tables: dict[str, Any] = {}
    for table_type in table_types:
        raise_if_cancelled(options.cancel_check)
        progress(f"Fetching table {table_type}...")
        tables[table_type] = client.fetch_table(
            report_input.code,
            table_type,
            fight_ids=fight_ids,
            allow_unlisted=options.allow_unlisted,
        )
    raise_if_cancelled(options.cancel_check)

    event_iterables: dict[str, Iterable[dict[str, Any]]] = {}
    for event_type in event_types:
        raise_if_cancelled(options.cancel_check)
        events = client.iter_events(
            report_input.code,
            event_type,
            fight_ids=fight_ids,
            start_time=start_time,
            end_time=end_time,
            limit=options.limit,
            allow_unlisted=options.allow_unlisted,
            filter_expression=options.filter_expression,
            max_pages=options.max_pages,
        )
        event_iterables[event_type] = event_progress(event_type, events, progress, options.cancel_check)

    out_dir = fresh_output_dir(options.out, str(report.get("code") or report_input.code), report.get("title"))
    progress(f"Writing bundle to {out_dir}...")
    try:
        out_dir, archive = export_bundle(
            out_dir=out_dir,
            report=report,
            fight_ids=fight_ids,
            tables=tables,
            events_by_type=event_iterables,
            source_url=options.report,
            make_zip=options.make_zip,
            archive_only=options.archive_only,
        )
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise

    return DownloadResult(
        out_dir=out_dir,
        archive=archive,
        report_code=str(report.get("code") or report_input.code),
        fight_ids=fight_ids,
    )


def event_progress(
    event_type: str,
    events: Iterable[dict[str, Any]],
    progress: ProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> Iterable[dict[str, Any]]:
    progress(f"Fetching events {event_type}...")
    count = 0
    for event in events:
        raise_if_cancelled(cancel_check)
        count += 1
        if count % 50_000 == 0:
            progress(f"Fetched {count} {event_type} events...")
        yield event
    progress(f"Fetched {count} {event_type} events.")


def resolve_type_list(value: str, standard: list[str]) -> list[str]:
    normalized = value.strip().lower()
    if normalized in {"", "none", "off", "false", "0"}:
        return []
    if normalized in {"standard", "default"}:
        return list(standard)
    return parse_list(value)


def resolve_event_type_list(value: str) -> list[str]:
    normalized = value.strip().lower()
    if normalized in {"", "none", "off", "false", "0", "compact", "standard", "default"}:
        return list(DEFAULT_EVENT_TYPES)
    if normalized in {"essential", "analysis"}:
        return list(ESSENTIAL_EVENT_TYPES)
    if normalized in {"full", "raw", "all"}:
        return list(FULL_EVENT_TYPES)
    return parse_list(value)


def getenv_any(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def option_difficulty_ids(
    difficulty_id: int | None,
    difficulty_ids: tuple[int, ...] | None,
) -> tuple[int, ...] | None:
    if difficulty_ids is not None:
        return difficulty_ids or None
    if difficulty_id is not None:
        return (difficulty_id,)
    return None


def raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check and cancel_check():
        raise DownloadCancelled("Download cancelled.")
