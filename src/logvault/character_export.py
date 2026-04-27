from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .api import WarcraftLogsClient
from .dates import parse_date_bound, report_timestamp_seconds
from .difficulty import difficulty_label
from .download import DownloadOptions, DownloadResult, download_report, getenv_any
from .env import load_env_file
from .exporter import safe_name, zip_bundle


@dataclass
class CharacterReportsOptions:
    character_name: str
    server_slug: str
    server_region: str
    difficulty_id: int | None = None
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


@dataclass
class CharacterReportsResult:
    out_dir: Path
    archive: Path | None
    downloaded: list[DownloadResult]
    skipped: list[dict[str, Any]]
    character: dict[str, Any]


def download_character_reports(
    options: CharacterReportsOptions,
    progress=None,
) -> CharacterReportsResult:
    progress = progress or (lambda _message: None)
    if options.archive_only and not options.make_zip:
        raise ValueError("Archive-only output requires zip archive creation.")
    if options.env_file is not None:
        load_env_file(options.env_file)

    start_ts = parse_date_bound(options.season_start)
    end_ts = parse_date_bound(options.season_end, end=True)
    if start_ts and end_ts and start_ts > end_ts:
        raise ValueError("Season start must be before season end.")

    client = WarcraftLogsClient(
        client_id=options.client_id or getenv_any("WCL_CLIENT_ID", "WARCRAFTLOGS_CLIENT_ID"),
        client_secret=options.client_secret or getenv_any("WCL_CLIENT_SECRET", "WARCRAFTLOGS_CLIENT_SECRET"),
        access_token=options.access_token or getenv_any("WCL_ACCESS_TOKEN", "WARCRAFTLOGS_ACCESS_TOKEN"),
        timeout=options.timeout,
    )

    progress(
        f"Finding reports for {options.character_name} on "
        f"{options.server_region}/{options.server_slug}..."
    )
    reports, character = collect_recent_reports(client, options, start_ts=start_ts, end_ts=end_ts, progress=progress)
    if not reports:
        raise ValueError("No reports matched the character/date filters.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_name = "-".join(
        part
        for part in [
            safe_name(options.character_name),
            safe_name(options.server_region),
            safe_name(options.server_slug),
            safe_name(difficulty_label(options.difficulty_id)),
            stamp,
        ]
        if part
    )
    out_dir = options.out / f"character-{batch_name}"
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[DownloadResult] = []
    skipped: list[dict[str, Any]] = []
    for index, report in enumerate(reports, start=1):
        code = str(report.get("code") or "")
        title = report.get("title") or code
        if not code:
            skipped.append({"code": "", "title": title, "reason": "missing report code"})
            continue
        progress(f"[{index}/{len(reports)}] Exporting report {code}: {title}")
        try:
            result = download_report(
                DownloadOptions(
                    report=code,
                    fight=options.fight,
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
                    difficulty_id=options.difficulty_id,
                ),
                progress=progress,
            )
        except ValueError as exc:
            skipped.append({"code": code, "title": title, "reason": str(exc)})
            progress(f"Skipped {code}: {exc}")
        else:
            downloaded.append(result)

    write_character_index(
        out_dir=out_dir,
        options=options,
        character=character,
        source_reports=reports,
        downloaded=downloaded,
        skipped=skipped,
    )
    archive = zip_bundle(out_dir) if options.make_zip else None
    if archive is not None and options.archive_only:
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
            code = str(report.get("code") or "")
            if code in seen_codes:
                continue
            report_ts = report_timestamp_seconds(report.get("startTime"))
            if end_ts is not None and report_ts is not None and report_ts > end_ts:
                continue
            if start_ts is not None and report_ts is not None and report_ts < start_ts:
                should_stop_for_date = True
                continue
            seen_codes.add(code)
            reports.append(report)
            if options.max_reports is not None and len(reports) >= options.max_reports:
                return reports, character

        if should_stop_for_date:
            return reports, character
        if not page_data.has_more_pages:
            return reports, character
        page += 1


def write_character_index(
    *,
    out_dir: Path,
    options: CharacterReportsOptions,
    character: dict[str, Any],
    source_reports: list[dict[str, Any]],
    downloaded: list[DownloadResult],
    skipped: list[dict[str, Any]],
) -> None:
    manifest = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "character": character,
        "filters": {
            "name": options.character_name,
            "serverSlug": options.server_slug,
            "serverRegion": options.server_region,
            "difficulty": difficulty_label(options.difficulty_id),
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
        rows.append(
            {
                "code": code,
                "title": report.get("title") or "",
                "startTime": report.get("startTime"),
                "endTime": report.get("endTime"),
                "zone": ((report.get("zone") or {}).get("name") or ""),
                "status": "downloaded" if result else "skipped",
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
        f"- Difficulty: {difficulty_label(options.difficulty_id)}",
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
