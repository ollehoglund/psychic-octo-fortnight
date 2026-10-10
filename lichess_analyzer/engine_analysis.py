"""Analyze chess games with Stockfish and identify costly moves."""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

import chess
import chess.engine
import chess.pgn


@dataclass(frozen=True)
class CriticalMistake:
    date: str
    opponent: str
    color: str
    move_number: int
    played_move: str
    best_move: str
    eval_loss_cp: int


def analyze_games_with_engine(
    pgn_text: str,
    username: str,
    engine_path: str,
    seconds_per_position: float = 0.2,
    threshold_cp: int = 200,
) -> list[CriticalMistake]:
    """Find moves that worsen the position by at least threshold_cp."""

    username = username.strip()
    if not username:
        raise ValueError("Username must not be empty")
    if seconds_per_position <= 0:
        raise ValueError("Analysis time must be positive")

    mistakes: list[CriticalMistake] = []
    stream = StringIO(pgn_text)
    game_number = 0

    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        while game := chess.pgn.read_game(stream):
            game_number += 1
            print(f"Stockfish: analyzing game {game_number}...", flush=True)

            if game.errors:
                raise ValueError(f"Could not parse PGN: {game.errors[0]}")

            headers = game.headers
            white = headers.get("White", "")
            black = headers.get("Black", "")

            is_white = white.casefold() == username.casefold()
            is_black = black.casefold() == username.casefold()

            if not is_white and not is_black:
                continue

            user_color = chess.WHITE if is_white else chess.BLACK
            opponent = black if is_white else white
            date = headers.get("UTCDate", headers.get("Date", "Unknown date"))

            board = game.board()
            pending = None

            def record_if_significant(after_info):
                if pending is None:
                    return

                after_score = after_info["score"].pov(
                    pending["color"]
                ).score(mate_score=10000)

                if after_score is None:
                    return

                loss = pending["before_score"] - after_score

                if pending["color"] == user_color and loss >= threshold_cp:
                    mistakes.append(
                        CriticalMistake(
                            date=date,
                            opponent=opponent or "Unknown opponent",
                            color="White" if is_white else "Black",
                            move_number=pending["move_number"],
                            played_move=pending["played_move"],
                            best_move=pending["best_move"],
                            eval_loss_cp=loss,
                        )
                    )

            for move in game.mainline_moves():
                info = engine.analyse(
                    board,
                    chess.engine.Limit(time=seconds_per_position),
                )

                record_if_significant(info)

                score = info["score"].pov(board.turn).score(
                    mate_score=10000
                )
                pv = info.get("pv", [])

                if score is None or not pv:
                    pending = None
                else:
                    pending = {
                        "color": board.turn,
                        "move_number": board.fullmove_number,
                        "played_move": board.san(move),
                        "best_move": board.san(pv[0]),
                        "before_score": score,
                    }

                board.push(move)

            if pending is not None:
                final_info = engine.analyse(
                    board,
                    chess.engine.Limit(time=seconds_per_position),
                )
                record_if_significant(final_info)

    return sorted(
        mistakes,
        key=lambda mistake: mistake.eval_loss_cp,
        reverse=True,
    )