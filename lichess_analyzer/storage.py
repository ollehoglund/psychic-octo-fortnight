
"""SQLite cache for downloaded Lichess games and Stockfish results."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import chess.pgn

DB_PATH = Path(__file__).resolve().parent.parent / "lichess_games.sqlite3"


def connect():
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with connect() as db:
        db.execute("""
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
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_games_username
            ON games(username)
        """)


def split_pgn(pgn_text: str) -> list[dict]:
    """Split an exported PGN file into independently stored games."""
    from io import StringIO

    stream = StringIO(pgn_text)
    games = []

    while game := chess.pgn.read_game(stream):
        if game.errors:
            raise ValueError(f"Invalid PGN: {game.errors[0]}")

        exporter = chess.pgn.StringExporter(
            headers=True,
            variations=False,
            comments=True,
        )
        single_pgn = game.accept(exporter) + "\n"
        headers = game.headers

        white = headers.get("White", "")
        black = headers.get("Black", "")
        date = headers.get("UTCDate", headers.get("Date", ""))

        games.append({
            "game_key": hashlib.sha256(
                single_pgn.encode("utf-8")
            ).hexdigest(),
            "date": date,
            "opponent": black if white else "",
            "result": headers.get("Result", "*"),
            "pgn": single_pgn,
        })

    return games


def save_new_games(username: str, pgn_text: str) -> int:
    """Insert newly seen games without overwriting existing analysis."""
    initialize_database()
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0

    with connect() as db:
        for game in split_pgn(pgn_text):
            cursor = db.execute(
                """
                INSERT OR IGNORE INTO games
                (game_key, username, date, opponent, result, pgn, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    game["game_key"],
                    username.casefold(),
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
    initialize_database()

    with connect() as db:
        rows = db.execute(
            """
            SELECT * FROM games
            WHERE username = ?
            ORDER BY date DESC, imported_at DESC
            """,
            (username.casefold(),),
        ).fetchall()

    return [dict(row) for row in rows]


def get_unanalyzed_games(username: str) -> list[dict]:
    initialize_database()

    with connect() as db:
        rows = db.execute(
            """
            SELECT * FROM games
            WHERE username = ? AND analysis_json IS NULL
            ORDER BY date DESC, imported_at DESC
            """,
            (username.casefold(),),
        ).fetchall()

    return [dict(row) for row in rows]


def save_analysis(game_key: str, mistakes: list[dict]) -> None:
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
    mistakes = []

    for game in get_games(username):
        if game["analysis_json"] is not None:
            mistakes.extend(json.loads(game["analysis_json"]))

    return sorted(
        mistakes,
        key=lambda item: item.get("eval_loss_cp", 0),
        reverse=True,
    )
