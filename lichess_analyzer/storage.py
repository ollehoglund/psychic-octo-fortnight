
"""SQLite cache for downloaded Lichess games and Stockfish results."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from io import StringIO

import chess
import chess.pgn


DB_PATH = Path(__file__).resolve().parent.parent / "lichess_games.sqlite3"


def is_standard_chess_pgn(pgn_text: str) -> bool:
    """Accept standard chess only; reject recognized variants."""
    game = chess.pgn.read_game(StringIO(pgn_text))

    if game is None or game.errors:
        return False

    return type(game.board()) is chess.Board


def get_opponent_from_pgn(pgn_text: str, username: str) -> str:
    """Return the opponent's username relative to the account username."""
    game = chess.pgn.read_game(StringIO(pgn_text))

    if game is None:
        return ""

    white = game.headers.get("White", "")
    black = game.headers.get("Black", "")
    target = username.strip().casefold()

    if white.casefold() == target:
        return black

    if black.casefold() == target:
        return white

    return ""


def connect():
    """Open a database connection with named-column access."""
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    """Create the games table and index if they don't exist."""
    with connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                game_key TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                date TEXT,
                opponent TEXT,
                result TEXT,
                pgn TEXT NOT NULL,
                analysis_json TEXT,
                analyzed_at TEXT,
                imported_at TEXT NOT NULL
            )
            """
        )

        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_games_username
            ON games(username)
            """
        )


def split_pgn(pgn_text: str) -> list[dict]:
    """Split an exported PGN file into independently stored games."""
    stream = StringIO(pgn_text)
    games = []

    while True:
        game = chess.pgn.read_game(stream)

        if game is None:
            break

        if game.errors:
            raise ValueError(f"Invalid PGN: {game.errors[0]}")

        exporter = chess.pgn.StringExporter(
            headers=True,
            variations=False,
            comments=True,
        )
        single_pgn = game.accept(exporter) + "\n"
        headers = game.headers

        games.append(
            {
                "game_key": hashlib.sha256(
                    single_pgn.encode("utf-8")
                ).hexdigest(),
                "date": headers.get(
                    "UTCDate", headers.get("Date", "")
                ),
                # Corrected using the account username when saving.
                "opponent": "",
                "result": headers.get("Result", "*"),
                "pgn": single_pgn,
            }
        )

    return games


def save_new_games(username: str, pgn_text: str) -> int:
    """Insert new standard games without overwriting saved analysis."""
    initialize_database()

    now = datetime.now(timezone.utc).isoformat()
    account = username.strip().casefold()
    new_count = 0

    with connect() as db:
        for game in split_pgn(pgn_text):
            if not is_standard_chess_pgn(game["pgn"]):
                continue

            game["opponent"] = get_opponent_from_pgn(
                game["pgn"], username
            )

            cursor = db.execute(
                """
                INSERT OR IGNORE INTO games
                (
                    game_key,
                    username,
                    date,
                    opponent,
                    result,
                    pgn,
                    imported_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game["game_key"],
                    account,
                    game["date"],
                    game["opponent"],
                    game["result"],
                    game["pgn"],
                    now,
                ),
            )

            new_count += cursor.rowcount

    return new_count


def get_games(username: str) -> list[dict]:
    """Return all cached games for an account, newest first."""
    initialize_database()

    with connect() as db:
        rows = db.execute(
            """
            SELECT *
            FROM games
            WHERE username = ?
            ORDER BY date DESC, imported_at DESC
            """,
            (username.strip().casefold(),),
        ).fetchall()

    return [dict(row) for row in rows]


def get_unanalyzed_games(
    username: str,
    opponent: str | None = None,
) -> list[dict]:
    """Return unanalyzed standard games, optionally filtered by opponent."""
    initialize_database()

    account = username.strip().casefold()
    target = opponent.strip().casefold() if opponent else None

    with connect() as db:
        rows = db.execute(
            """
            SELECT *
            FROM games
            WHERE username = ?
              AND analysis_json IS NULL
            ORDER BY date DESC, imported_at DESC
            """,
            (account,),
        ).fetchall()

        games = []

        for row in rows:
            game = dict(row)

            if not is_standard_chess_pgn(game["pgn"]):
                continue

            actual_opponent = get_opponent_from_pgn(
                game["pgn"], username
            )

            # Repair the opponent field for previously imported games.
            if game["opponent"] != actual_opponent:
                db.execute(
                    """
                    UPDATE games
                    SET opponent = ?
                    WHERE game_key = ?
                      AND username = ?
                    """,
                    (
                        actual_opponent,
                        game["game_key"],
                        account,
                    ),
                )
                game["opponent"] = actual_opponent

            if (
                target
                and actual_opponent.strip().casefold() != target
            ):
                continue

            games.append(game)

    return games


def save_analysis(game_key: str, mistakes: list[dict]) -> None:
    """Save analysis results for a game."""
    now = datetime.now(timezone.utc).isoformat()

    with connect() as db:
        db.execute(
            """
            UPDATE games
            SET analysis_json = ?, analyzed_at = ?
            WHERE game_key = ?
            """,
            (json.dumps(mistakes), now, game_key),
        )


def get_saved_mistakes(username: str) -> list[dict]:
    """Return saved mistakes across analyzed games, ranked by severity."""
    mistakes = []

    for game in get_games(username):
        if game["analysis_json"] is not None:
            mistakes.extend(json.loads(game["analysis_json"]))

    return sorted(
        mistakes,
        key=lambda item: (
            bool(item.get("mate_related", False)),
            int(item.get("eval_loss_cp") or 0),
        ),
        reverse=True,
    )
