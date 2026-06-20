from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .api import WarcraftLogsClient
from .content import content_scope_label, report_matches_content, validate_content_filters
from .dates import parse_date_bound, report_timestamp_seconds
from .difficulty import difficulty_scope_label
from .download import (
    DownloadOptions,
    DownloadResult,
    download_report,
    getenv_any,
    option_difficulty_ids,
    raise_if_cancelled,
    select_report_fights,
)
from .env import load_env_file
from .errors import WarcraftLogsError
from .exporter import report_output_dir, safe_name, zip_bundle
from .essential import (
    MythicPlusFight,
    essential_includes_mythic_plus,
    essential_includes_raid,
    extract_mythic_plus_fights,
    mythic_plus_target_levels,
    mythic_plus_targets_summary,
    select_mythic_raid_fight_ids,
)


@dataclass
class CharacterReportsOptions:
    character_name: str
    server_slug: str
    server_region: str
    difficulty_id: int | None = None
    difficulty_ids: tuple[int, ...] | None = None
    encounter: str | None = None
    content_scope: str | None = None
    zone_filter: str | None = None
    essential_mode: bool = False
    completed_only: bool = True
    season_start: str | None = None
    season_end: str | None = None
    max_reports: int | None = None
    page_limit: int = 100
    fight: str | None = "boss"
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
    cancel_check: Callable[[], bool] | None = None


@dataclass
class CharacterReportsResult:
    out_dir: Path
    archive: Path | None
    downloaded: list[DownloadResult]
    skipped: list[dict[str, Any]]
    character: dict[str, Any]


@dataclass
class PlannedReport:
    source: dict[str, Any]
    metadata: dict[str, Any]
    fight_ids: list[int]
    out_dir: Path


@dataclass
class EssentialCandidate:
    index: int
    source: dict[str, Any]
    metadata: dict[str, Any]
    kind: str
    raid_fight_ids: list[int] | None = None
    mythic_plus_fights: list[MythicPlusFight] | None = None


def download_character_reports(
    options: CharacterReportsOptions,
    progress=None,
) -> CharacterReportsResult:
    progress = progress or (lambda _message: None)
    if options.archive_only and not options.make_zip:
        raise ValueError("Archive-only output requires zip archive creation.")
    if options.env_file is not None:
        load_env_file(options.env_file)
    raise_if_cancelled(options.cancel_check)
    validate_content_filters(options.content_scope, options.zone_filter)

    start_ts = parse_date_bound(options.season_start)
    end_ts = parse_date_bound(options.season_end, end=True)
    if start_ts and end_ts and start_ts > end_ts:
        raise ValueError("Season start must be before season end.")

    client = WarcraftLogsClient(
        client_id=options.client_id or getenv_any("WCL_CLIENT_ID", "WARCRAFTLOGS_CLIENT_ID"),
        client_secret=options.client_secret or getenv_any("WCL_CLIENT_SECRET", "WARCRAFTLOGS_CLIENT_SECRET"),
        access_token=options.access_token or getenv_any("WCL_ACCESS_TOKEN", "WARCRAFTLOGS_ACCESS_TOKEN"),
        timeout=options.timeout,
        retry_callback=progress,
        cancel_check=options.cancel_check,
    )

    progress(
        f"Finding reports for {options.character_name} on "
        f"{options.server_region}/{options.server_slug}..."
    )
    source_reports, character = collect_recent_reports(client, options, start_ts=start_ts, end_ts=end_ts, progress=progress)
    if not source_reports:
        raise ValueError("No reports matched the character/date filters.")

    batch_name = "-".join(
        part
        for part in [
            safe_name(options.character_name),
            safe_name(options.server_region),
            safe_name(options.server_slug),
            safe_name(content_scope_label(options.content_scope)),
            safe_name(options.zone_filter or ""),
            "essential" if options.essential_mode else "",
            safe_name(character_difficulty_label(options)),
            safe_name(options.encounter or ""),
            "completed" if character_completed_only(options) else "all-fights",
        ]
        if part
    )
    out_dir = options.out / f"character-{batch_name}"
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    planned, skipped = scan_exportable_reports(
        client=client,
        options=options,
        source_reports=source_reports,
        reports_dir=reports_dir,
        progress=progress,
    )
    scan_skipped_count = len(skipped)
    write_character_index(
        out_dir=out_dir,
        options=options,
        character=character,
        source_reports=source_reports,
        downloaded=[],
        skipped=skipped,
        planned_report_codes={str(item.metadata.get("code") or item.source.get("code") or "") for item in planned},
    )
    progress(f"Scan complete: {len(planned)} exportable reports to export; {len(skipped)} skipped.")
    if not planned:
        raise ValueError("No exportable reports matched the selected filters.")

    downloaded: list[DownloadResult] = []
    for index, item in enumerate(planned, start=1):
        raise_if_cancelled(options.cancel_check)
        code = str(item.metadata.get("code") or item.source.get("code") or "")
        title = item.metadata.get("title") or item.source.get("title") or code
        if export_complete(item.out_dir, code, item.fight_ids):
            progress(f"[{index}/{len(planned)}] Already exported {code}: {title}")
            downloaded.append(DownloadResult(out_dir=item.out_dir, archive=None, report_code=code, fight_ids=item.fight_ids))
            continue
        progress(f"[{index}/{len(planned)}] Exporting report {code}: {title}")
        try:
            planned_fight_selector = ",".join(str(fight_id) for fight_id in item.fight_ids)
            result = download_report(
                DownloadOptions(
                    report=code,
                    fight=planned_fight_selector if options.essential_mode else options.fight,
                    include_trash=options.include_trash,
                    tables=options.tables,
                    events=options.events,
                    filter_expression=options.filter_expression,
                    out=reports_dir,
                    make_zip=False,
                    limit=options.limit,
                    max_pages=options.max_pages,
                    allow_unlisted=options.allow_unlisted,
                    client_id=options.client_id,
                    client_secret=options.client_secret,
                    access_token=options.access_token,
                    timeout=options.timeout,
                    env_file=options.env_file,
                    difficulty_id=None if options.essential_mode else options.difficulty_id,
                    difficulty_ids=None if options.essential_mode else options.difficulty_ids,
                    encounter=None if options.essential_mode else options.encounter,
                    content_scope=options.content_scope,
                    zone_filter=options.zone_filter,
                    completed_only=True if options.essential_mode else options.completed_only,
                    output_dir=item.out_dir,
                    cancel_check=options.cancel_check,
                ),
                progress=progress,
            )
        except (ValueError, WarcraftLogsError) as exc:
            skipped.append({"code": code, "title": title, "reason": str(exc)})
            progress(f"Skipped {code}: {exc}")
        else:
            downloaded.append(result)
        write_character_index(
            out_dir=out_dir,
            options=options,
            character=character,
            source_reports=source_reports,
            downloaded=downloaded,
            skipped=skipped,
            planned_report_codes={str(item.metadata.get("code") or item.source.get("code") or "") for item in planned},
        )

    write_character_index(
        out_dir=out_dir,
        options=options,
        character=character,
        source_reports=source_reports,
        downloaded=downloaded,
        skipped=skipped,
        planned_report_codes={str(item.metadata.get("code") or item.source.get("code") or "") for item in planned},
    )
    archive = zip_bundle(out_dir) if options.make_zip else None
    download_skipped = skipped[scan_skipped_count:]
    if archive is not None and options.archive_only and not download_skipped:
        shutil.rmtree(out_dir)
    return CharacterReportsResult(
        out_dir=out_dir,
        archive=archive,
        downloaded=downloaded,
        skipped=skipped,
        character=character,
    )


def collect_recent_reports(
    client: WarcraftLogsClient,
    options: CharacterReportsOptions,
    *,
    start_ts: float | None,
    end_ts: float | None,
    progress,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    page = 1
    reports: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    character: dict[str, Any] = {}
    page_limit = max(1, min(options.page_limit, 100))

    while True:
        raise_if_cancelled(options.cancel_check)
        page_data = client.fetch_character_recent_reports(
            name=options.character_name,
            server_slug=options.server_slug,
            server_region=options.server_region,
            limit=page_limit,
            page=page,
        )
        character = page_data.character
        progress(f"Fetched report list page {page} ({len(page_data.reports)} reports).")

        should_stop_for_date = False
        for report in page_data.reports:
            raise_if_cancelled(options.cancel_check)
            code = str(report.get("code") or "")
            if code in seen_codes:
                continue
            report_ts = report_timestamp_seconds(report.get("startTime"))
            if end_ts is not None and report_ts is not None and report_ts > end_ts:
                continue
            if start_ts is not None and report_ts is not None and report_ts < start_ts:
                should_stop_for_date = True
                continue
            if not report_matches_content(
                report,
                content_scope=options.content_scope,
                zone_filter=options.zone_filter,
                allow_unknown=True,
            ):
                continue
            seen_codes.add(code)
            reports.append(report)

        if should_stop_for_date:
            return reports, character
        if not page_data.has_more_pages:
            return reports, character
        page += 1


def scan_exportable_reports(
    *,
    client: WarcraftLogsClient,
    options: CharacterReportsOptions,
    source_reports: list[dict[str, Any]],
    reports_dir: Path,
    progress,
) -> tuple[list[PlannedReport], list[dict[str, Any]]]:
    if options.essential_mode:
        return scan_essential_reports(
            client=client,
            options=options,
            source_reports=source_reports,
            reports_dir=reports_dir,
            progress=progress,
        )

    progress(f"Scanning {len(source_reports)} candidate reports for exportable fights...")
    planned: list[PlannedReport] = []
    skipped: list[dict[str, Any]] = []
    for index, report in enumerate(source_reports, start=1):
        raise_if_cancelled(options.cancel_check)
        code = str(report.get("code") or "")
        title = report.get("title") or code
        if not code:
            skipped.append({"code": "", "title": title, "reason": "missing report code"})
            continue
        progress(f"Scanning report {index}/{len(source_reports)}: {code}")
        try:
            metadata = client.fetch_report_metadata(code, allow_unlisted=options.allow_unlisted)
            if not report_matches_content(
                metadata,
                content_scope=options.content_scope,
                zone_filter=options.zone_filter,
            ):
                skipped.append({"code": code, "title": title, "reason": "content filters"})
                continue
            _, fight_ids = select_report_fights(
                metadata,
                DownloadOptions(
                    report=code,
                    fight=options.fight,
                    include_trash=options.include_trash,
                    difficulty_id=options.difficulty_id,
                    difficulty_ids=options.difficulty_ids,
                    encounter=options.encounter,
                    completed_only=options.completed_only,
                ),
            )
        except (ValueError, WarcraftLogsError) as exc:
            skipped.append({"code": code, "title": title, "reason": str(exc)})
            continue
        planned.append(
            PlannedReport(
                source=report,
                metadata=metadata,
                fight_ids=fight_ids,
                out_dir=report_output_dir(reports_dir, code, metadata.get("title") or title),
            )
        )
        if options.max_reports is not None and len(planned) >= options.max_reports:
            break
    return planned, skipped


def scan_essential_reports(
    *,
    client: WarcraftLogsClient,
    options: CharacterReportsOptions,
    source_reports: list[dict[str, Any]],
    reports_dir: Path,
    progress,
) -> tuple[list[PlannedReport], list[dict[str, Any]]]:
    progress(
        "Essential mode: scanning candidates for Mythic raid kills and timed Mythic+ target levels..."
    )
    candidates: list[EssentialCandidate] = []
    skipped: list[dict[str, Any]] = []
    all_mythic_plus_fights: list[MythicPlusFight] = []

    for index, report in enumerate(source_reports, start=1):
        raise_if_cancelled(options.cancel_check)
        code = str(report.get("code") or "")
        title = report.get("title") or code
        if not code:
            skipped.append({"code": "", "title": title, "reason": "missing report code"})
            continue

        progress(f"Scanning report {index}/{len(source_reports)}: {code}")
        try:
            metadata = client.fetch_report_metadata(code, allow_unlisted=options.allow_unlisted)
        except WarcraftLogsError as exc:
            skipped.append({"code": code, "title": title, "reason": str(exc)})
            continue

        if not report_matches_content(
            metadata,
            content_scope=options.content_scope,
            zone_filter=options.zone_filter,
        ):
            skipped.append({"code": code, "title": title, "reason": "content filters"})
            continue

        mythic_plus_fights = (
            extract_mythic_plus_fights(metadata, completed_only=True)
            if essential_includes_mythic_plus(options.content_scope)
            else []
        )
        if mythic_plus_fights:
            all_mythic_plus_fights.extend(mythic_plus_fights)
            candidates.append(
                EssentialCandidate(
                    index=index,
                    source=report,
                    metadata=metadata,
                    kind="mythic_plus",
                    mythic_plus_fights=mythic_plus_fights,
                )
            )
            continue

        raid_fight_ids = (
            select_mythic_raid_fight_ids(metadata, completed_only=True)
            if essential_includes_raid(options.content_scope)
            else []
        )
        if raid_fight_ids:
            candidates.append(
                EssentialCandidate(
                    index=index,
                    source=report,
                    metadata=metadata,
                    kind="raid",
                    raid_fight_ids=raid_fight_ids,
                )
            )
            continue

        skipped.append({"code": code, "title": title, "reason": "essential mode filters"})

    targets = mythic_plus_target_levels(all_mythic_plus_fights)
    if targets:
        progress(f"Essential mode Mythic+ targets: {mythic_plus_targets_summary(all_mythic_plus_fights, targets)}")

    planned: list[PlannedReport] = []
    for candidate in sorted(candidates, key=lambda item: item.index):
        code = str(candidate.metadata.get("code") or candidate.source.get("code") or "")
        title = candidate.metadata.get("title") or candidate.source.get("title") or code
        if candidate.kind == "mythic_plus":
            selected_fights = [
                fight
                for fight in candidate.mythic_plus_fights or []
                if fight.level in targets.get(fight.dungeon_key, set())
            ]
            fight_ids = [fight.fight_id for fight in selected_fights]
            if not fight_ids:
                skipped.append({"code": code, "title": title, "reason": "essential Mythic+ level filter"})
                continue
        else:
            fight_ids = list(candidate.raid_fight_ids or [])

        planned.append(
            PlannedReport(
                source=candidate.source,
                metadata=candidate.metadata,
                fight_ids=fight_ids,
                out_dir=report_output_dir(reports_dir, code, title),
            )
        )
        if options.max_reports is not None and len(planned) >= options.max_reports:
            break

    return planned, skipped


def export_complete(out_dir: Path, report_code: str, fight_ids: list[int]) -> bool:
    metadata_path = out_dir / "metadata.json"
    summary_path = out_dir / "summary.md"
    if not metadata_path.is_file() or not summary_path.is_file():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    exported_code = str((metadata.get("report") or {}).get("code") or "")
    exported_fights = [int(value) for value in metadata.get("selectedFightIDs") or []]
    return exported_code == report_code and exported_fights == fight_ids


def write_character_index(
    *,
    out_dir: Path,
    options: CharacterReportsOptions,
    character: dict[str, Any],
    source_reports: list[dict[str, Any]],
    downloaded: list[DownloadResult],
    skipped: list[dict[str, Any]],
    planned_report_codes: set[str] | None = None,
) -> None:
    planned_report_codes = planned_report_codes or set()
    manifest = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "character": character,
        "filters": {
            "name": options.character_name,
            "serverSlug": options.server_slug,
            "serverRegion": options.server_region,
            "contentScope": content_scope_label(options.content_scope),
            "zoneTier": options.zone_filter,
            "essentialMode": options.essential_mode,
            "difficulty": character_difficulty_label(options),
            "encounter": options.encounter,
            "completedOnly": character_completed_only(options),
            "seasonStart": options.season_start,
            "seasonEnd": options.season_end,
            "maxReports": options.max_reports,
        },
        "sourceReports": source_reports,
        "downloaded": [
            {
                "reportCode": result.report_code,
                "outDir": str(result.out_dir.relative_to(out_dir)),
                "fightIDs": result.fight_ids,
            }
            for result in downloaded
        ],
        "skipped": skipped,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    rows = []
    by_code = {result.report_code: result for result in downloaded}
    skipped_by_code = {str(item.get("code") or ""): item for item in skipped}
    for report in source_reports:
        code = str(report.get("code") or "")
        result = by_code.get(code)
        skipped_item = skipped_by_code.get(code)
        if result:
            status = "downloaded"
        elif skipped_item:
            status = "skipped"
        elif code in planned_report_codes:
            status = "pending"
        else:
            status = "filtered"
        rows.append(
            {
                "code": code,
                "title": report.get("title") or "",
                "startTime": report.get("startTime"),
                "endTime": report.get("endTime"),
                "zone": ((report.get("zone") or {}).get("name") or ""),
                "status": status,
                "folder": str(result.out_dir.relative_to(out_dir)) if result else "",
                "reason": skipped_item.get("reason", "") if skipped_item else "",
            }
        )
    with (out_dir / "reports.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()) if rows else ["code"])
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        f"# {options.character_name} - Warcraft Logs export",
        "",
        f"- Server: `{options.server_region}/{options.server_slug}`",
        f"- Game mode: {content_scope_label(options.content_scope)}",
        f"- Zone/tier: {options.zone_filter or 'all'}",
        f"- Essential mode: {'yes' if options.essential_mode else 'no'}",
        f"- Difficulty: {character_difficulty_label(options)}",
        f"- Encounter: {options.encounter or 'all'}",
        f"- Completed only: {'yes' if character_completed_only(options) else 'no'}",
        f"- Season start: {options.season_start or 'not set'}",
        f"- Season end: {options.season_end or 'not set'}",
        f"- Reports matched: {len(source_reports)}",
        f"- Reports exported: {len(downloaded)}",
        f"- Reports skipped: {len(skipped)}",
        "",
        "## Reports",
        "",
        "| code | title | status | folder / reason |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        detail = row["folder"] or row["reason"]
        lines.append(f"| {row['code']} | {escape_md(row['title'])} | {row['status']} | {escape_md(detail)} |")
    (out_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def character_difficulty_label(options: CharacterReportsOptions) -> str:
    if options.essential_mode:
        return "Essential preset (raid Mythic)"
    return difficulty_scope_label(option_difficulty_ids(options.difficulty_id, options.difficulty_ids))


def character_completed_only(options: CharacterReportsOptions) -> bool:
    return True if options.essential_mode else options.completed_only
