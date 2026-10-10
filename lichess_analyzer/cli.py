"""Command-line entry point for Lichess game analysis."""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from .analysis import analyze_pgn, render_report
from .client import LichessAPIError, fetch_user_games


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Analyze games exported from Lichess.")
    parser.add_argument(
        "username",
        nargs="?",
        default=os.environ.get("LICHESS_USERNAME"),
        help="Lichess username (defaults to LICHESS_USERNAME from .env)",
    )
    parser.add_argument("--max-games", type=int, default=20, help="number of recent games to fetch (default: 20)")
    args = parser.parse_args()
    if not args.username:
        parser.error("provide a username or set LICHESS_USERNAME in .env")

    try:
        pgn_text = fetch_user_games(
            args.username,
            max_games=args.max_games,
            token=os.environ.get("LICHESS_TOKEN"),
        )
        report = analyze_pgn(pgn_text, args.username)
    except (LichessAPIError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")

    print(render_report(report))
    return 0