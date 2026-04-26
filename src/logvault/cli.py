from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
    parser.add_argument("report", help="Warcraft Logs report URL or raw report code.")
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
        default="standard",
        help="Comma-separated EventDataType values, 'standard', or 'none'. Default: standard.",
    )
    parser.add_argument("--filter", help="Optional Warcraft Logs filterExpression applied to events.")
    parser.add_argument("--out", default="exports", help="Output directory. Default: exports.")
    parser.add_argument("--no-zip", action="store_true", help="Do not create a .zip archive next to the output folder.")
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

    print(f"Done: {result.out_dir}")
    if result.archive:
        print(f"Archive: {result.archive}")
    return 0
