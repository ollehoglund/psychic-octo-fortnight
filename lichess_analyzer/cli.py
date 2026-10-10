"""Command-line entry point for Lichess game analysis."""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from .analysis import analyze_pgn, render_report
from .client import LichessAPIError, fetch_user_games

from .engine_analysis import analyze_games_with_engine
import chess.engine

def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Analyze games exported from Lichess.")
    parser.add_argument(
        "username",
        nargs="?",
        default=os.environ.get("LICHESS_USERNAME"),
        help="Lichess username (defaults to LICHESS_USERNAME from .env)",
    )
    parser.add_argument(
    "--max-games", type=int, 
    default=20, help="number of recent games to fetch (default: 20)")
    parser.add_argument(
    "--engine-analysis",
    action="store_true",
    help="analyze games with Stockfish",
    )
    parser.add_argument(
    "--engine-time",
    type=float,
    default=0.2,
    help="seconds per position for Stockfish (default: 0.2)",
    )
    
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
    if args.engine_analysis:
        engine_path = os.environ.get("STOCKFISH_PATH")

        if not engine_path:
            parser.error("set STOCKFISH_PATH in your .env file")

        try:
            mistakes = analyze_games_with_engine(
                pgn_text,
                args.username,
                engine_path,
                seconds_per_position=args.engine_time,
            )
        except (chess.engine.EngineError, OSError, ValueError) as error:
            parser.exit(1, f"Engine analysis error: {error}\n")

        print("\nStockfish: largest evaluation drops")
        if not mistakes:
            print("No moves exceeded the 2.0-pawn threshold.")
        else:
            for mistake in mistakes[:15]:
                print(
                    f"{mistake.date} | vs {mistake.opponent} | "
                    f"{mistake.color} move {mistake.move_number}: "
                    f"{mistake.played_move} -> best "
                    f"{mistake.best_move} | "
                    f"loss ~{mistake.eval_loss_cp / 100:.1f} pawns"
                )
    return 0