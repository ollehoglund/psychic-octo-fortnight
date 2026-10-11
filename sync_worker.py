
"""Download new games and analyze only games not already cached."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict

import chess.engine
from dotenv import load_dotenv

from lichess_analyzer.client import fetch_user_games
from lichess_analyzer.engine_analysis import analyze_games_with_engine
from lichess_analyzer.storage import (
    get_unanalyzed_games,
    save_analysis,
    save_new_games,
)


def run_sync(
    username: str,
    max_games: int = 40,
    engine_time: float = 0.1,
    opponent: str | None = None,
) -> None:
    load_dotenv()

    engine_path = os.environ.get("STOCKFISH_PATH")
    if not engine_path or not os.path.isfile(engine_path):
        raise ValueError("Check STOCKFISH_PATH in your .env file.")

    print(f"Downloading recent games for {username}...")
    pgn_text = fetch_user_games(
        username,
        max_games=max_games,
        token=os.environ.get("LICHESS_TOKEN"),
        opponent=opponent,
    )

    added = save_new_games(username, pgn_text)
    print(f"Downloaded games saved. Newly imported: {added}")

    pending = get_unanalyzed_games(username)
    print(f"Games awaiting analysis: {len(pending)}")

    for index, game in enumerate(pending, start=1):
        print(
            f"[{index}/{len(pending)}] "
            f"Analyzing {game['date']} vs {game['opponent']}..."
        )

        mistakes = analyze_games_with_engine(
            game["pgn"],
            username,
            engine_path,
            seconds_per_position=engine_time,
        )

        save_analysis(
            game["game_key"],
            [asdict(mistake) for mistake in mistakes],
        )

        print(f"Saved analysis for game {index}.")

    print("Sync and analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-games", type=int, default=40
    )
    parser.add_argument(
        "--engine-time", type=float, default=0.1
    )
    parser.add_argument(
    "--opponent",
    type=str,
    default=None,
    help="Only download and analyze games against this Lichess username",
)
    args = parser.parse_args()

    load_dotenv()
    username = os.environ.get("LICHESS_USERNAME")

    if not username:
        parser.error("Set LICHESS_USERNAME in your .env file.")

    try:
        run_sync(
            username,
            max_games=args.max_games,
            engine_time=args.engine_time,
        )
    except (
        ValueError,
        OSError,
        chess.engine.EngineError,
    ) as error:
        parser.exit(1, f"Sync failed: {error}\n")
