from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .character_export import CharacterReportsOptions, download_character_reports
from .content import CONTENT_SCOPE_CHOICES, parse_content_scope
from .difficulty import DIFFICULTY_SCOPE_CHOICES, parse_difficulty_scope
from .download import DownloadOptions, download_report
from .errors import LogVaultError


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return run_download(args)
    except (LogVaultError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="logvault",
        description="Download a Warcraft Logs report into a local readable bundle.",
    )
    parser.add_argument("report", nargs="?", help="Warcraft Logs report URL or raw report code.")
    parser.add_argument("--character", help="Download recent reports for this character instead of a single report.")
    parser.add_argument("--server", help="Realm slug for --character, e.g. draenor or howling-fjord.")
    parser.add_argument("--region", default="eu", help="Server region for --character: us, eu, kr, tw, cn. Default: eu.")
    parser.add_argument(
        "--content",
        default="all",
        help=(
            f"Game mode/content scope: {', '.join(CONTENT_SCOPE_CHOICES)}. "
            "Use --zone with custom zone/tier. Default: all."
        ),
    )
    parser.add_argument("--zone", help="Optional zone or raid tier filter, for example Sporefall or a zone ID.")
    parser.add_argument(
        "--difficulty",
        default="all",
        help=(
            f"Difficulty scope: {', '.join(DIFFICULTY_SCOPE_CHOICES)}, or a comma/plus-separated list. "
            "Example: mythic+heroic. Default: all."
        ),
    )
    parser.add_argument("--encounter", help="Only export one encounter. Accepts encounter ID or boss name.")
    parser.add_argument(
        "--include-unfinished",
        action="store_true",
        help="Include unfinished pulls/runs. Default exports only completed fights.",
    )
    parser.add_argument("--season-start", help="Character batch start date, YYYY-MM-DD.")
    parser.add_argument("--season-end", help="Character batch end date, YYYY-MM-DD.")
    parser.add_argument(
        "--max-reports",
        type=int,
        default=0,
        help="Maximum character reports to export. 0 means no local cap. Default: 0.",
    )
    parser.add_argument("--fight", help="Fight selector: 12, 12,13, last, boss, or all. URL #fight= is used by default.")
    parser.add_argument(
        "--include-trash",
        action="store_true",
        help="When no --fight is provided, export all fights including trash. Default exports boss fights only.",
    )
    parser.add_argument(
        "--tables",
        default="standard",
        help="Comma-separated TableDataType values, 'standard', or 'none'. Default: standard.",
    )
    parser.add_argument(
        "--events",
        default="compact",
        help=(
            "Event export preset: compact/none, essential, full, or comma-separated EventDataType values. "
            "Default: compact. full can still create very large exports."
        ),
    )
    parser.add_argument("--filter", help="Optional Warcraft Logs filterExpression applied to events.")
    parser.add_argument("--out", default="exports", help="Output directory. Default: exports.")
    parser.add_argument("--no-zip", action="store_true", help="Do not create a .zip archive next to the output folder.")
    parser.add_argument(
        "--archive-only",
        action="store_true",
        help="Create the .zip bundle and remove the extracted folder after export.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10_000,
        help="Events per API page. Warcraft Logs may cap this server-side. Default: 10000.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Maximum event pages per event type, useful for testing. 0 means no local cap.",
    )
    parser.add_argument(
        "--no-allow-unlisted",
        action="store_true",
        help="Do not pass allowUnlisted=true to Warcraft Logs report queries.",
    )
    parser.add_argument("--client-id", help="Warcraft Logs OAuth client id. Overrides env.")
    parser.add_argument("--client-secret", help="Warcraft Logs OAuth client secret. Overrides env.")
    parser.add_argument("--access-token", help="Use an existing bearer token instead of client credentials.")
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout in seconds. Default: 60.")
    return parser


def run_download(args: argparse.Namespace) -> int:
    content_scope = parse_content_scope(args.content)
    difficulty_ids = parse_difficulty_scope(args.difficulty)
    if args.character:
        if not args.server:
            raise ValueError("--server is required with --character.")
        result = download_character_reports(
            CharacterReportsOptions(
                character_name=args.character,
                server_slug=args.server,
                server_region=args.region,
                content_scope=content_scope,
                zone_filter=args.zone,
                completed_only=not args.include_unfinished,
                difficulty_ids=difficulty_ids,
                encounter=args.encounter,
                season_start=args.season_start,
                season_end=args.season_end,
                max_reports=args.max_reports or None,
                fight=args.fight or "boss",
                include_trash=args.include_trash,
                tables=args.tables,
                events=args.events,
                filter_expression=args.filter,
                out=Path(args.out),
                make_zip=not args.no_zip,
                archive_only=args.archive_only,
                limit=args.limit,
                max_pages=args.max_pages or None,
                allow_unlisted=not args.no_allow_unlisted,
                client_id=args.client_id,
                client_secret=args.client_secret,
                access_token=args.access_token,
                timeout=args.timeout,
            ),
            progress=lambda message: print(message, file=sys.stderr),
        )
        print(f"Done: {primary_output(result.out_dir, result.archive)}")
        if result.archive:
            print(f"Archive: {result.archive}")
        print(f"Exported reports: {len(result.downloaded)}; skipped: {len(result.skipped)}")
        return 0

    if not args.report:
        raise ValueError("report is required unless --character is used.")

    result = download_report(
        DownloadOptions(
            report=args.report,
            fight=args.fight,
            include_trash=args.include_trash,
            tables=args.tables,
            events=args.events,
            filter_expression=args.filter,
            out=Path(args.out),
            make_zip=not args.no_zip,
            archive_only=args.archive_only,
            limit=args.limit,
            max_pages=args.max_pages or None,
            allow_unlisted=not args.no_allow_unlisted,
            client_id=args.client_id,
            client_secret=args.client_secret,
            access_token=args.access_token,
            timeout=args.timeout,
            content_scope=content_scope,
            zone_filter=args.zone,
            completed_only=not args.include_unfinished,
            difficulty_ids=difficulty_ids,
            encounter=args.encounter,
        ),
        progress=lambda message: print(message, file=sys.stderr),
    )

    print(f"Done: {primary_output(result.out_dir, result.archive)}")
    if result.archive:
        print(f"Archive: {result.archive}")
    return 0


def primary_output(out_dir: Path, archive: Path | None) -> Path:
    if out_dir.exists():
        return out_dir
    if archive is not None:
        return archive
    return out_dir
