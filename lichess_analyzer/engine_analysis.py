
"""Analyze chess games with Stockfish and identify costly moves.

Centipawn losses and forced-mate changes are handled separately.
A mate-related mistake has eval_loss_cp=None rather than a fabricated
large centipawn value.
"""

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
    eval_loss_cp: int | None
    mate_related: bool = False
    mate_in_before: int | None = None
    mate_in_after: int | None = None


def assess_loss(
    before: chess.engine.PovScore,
    after: chess.engine.PovScore,
    threshold_cp: int,
) -> tuple[int | None, bool, int | None, int | None]:
    """Return centipawn loss, mate flag, and signed mate scores.

    Scores are expressed from the perspective of the player who made
    the move. Positive mate values mean that player can force mate;
    negative values mean their opponent can force mate.
    """
    before_mate = before.mate()
    after_mate = after.mate()

    # Only compare centipawns when neither position has a mate score.
    if before_mate is None and after_mate is None:
        before_cp = before.score()
        after_cp = after.score()

        if before_cp is None or after_cp is None:
            return None, False, None, None

        loss = before_cp - after_cp
        if loss >= threshold_cp:
            return loss, False, None, None

        return None, False, None, None

    # A move is mate-related when it worsens the forced-mate outcome:
    # - gives the opponent a forced mate;
    # - throws away our own forced mate;
    # - allows an existing forced mate against us to arrive sooner.
    mate_blunder = False

    if after_mate is not None and after_mate < 0:
        if before_mate is None or before_mate >= 0:
            mate_blunder = True
        elif abs(after_mate) < abs(before_mate):
            mate_blunder = True

    if before_mate is not None and before_mate > 0:
        if after_mate is None or after_mate <= 0:
            mate_blunder = True

    if mate_blunder:
        return None, True, before_mate, after_mate

    return None, False, before_mate, after_mate


def analyze_games_with_engine(
    pgn_text: str,
    username: str,
    engine_path: str,
    seconds_per_position: float = 0.2,
    threshold_cp: int = 200,
) -> list[CriticalMistake]:
    """Find significant centipawn losses and mate-related blunders."""

    username = username.strip()
    if not username:
        raise ValueError("Username must not be empty")
    if seconds_per_position <= 0:
        raise ValueError("Analysis time must be positive")

    mistakes: list[CriticalMistake] = []
    stream = StringIO(pgn_text)

    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        game_number = 0

        while game := chess.pgn.read_game(stream):
            game_number += 1
            print(
                f"Stockfish: analyzing game {game_number}...",
                flush=True,
            )

            if game.errors:
                raise ValueError(
                    f"Could not parse PGN: {game.errors[0]}"
                )

            headers = game.headers
            white = headers.get("White", "")
            black = headers.get("Black", "")

            is_white = white.casefold() == username.casefold()
            is_black = black.casefold() == username.casefold()

            if not is_white and not is_black:
                continue

            user_color = chess.WHITE if is_white else chess.BLACK
            opponent = black if is_white else white
            date = headers.get(
                "UTCDate",
                headers.get("Date", "Unknown date"),
            )

            board = game.board()
            pending = None

            def record_if_significant(after_info):
                if pending is None:
                    return

                after_score = after_info["score"].pov(
                    pending["color"]
                )

                loss_cp, mate_related, mate_before, mate_after = (
                    assess_loss(
                        pending["before_score"],
                        after_score,
                        threshold_cp,
                    )
                )

                if (
                    pending["color"] == user_color
                    and (loss_cp is not None or mate_related)
                ):
                    mistakes.append(
                        CriticalMistake(
                            date=date,
                            opponent=opponent or "Unknown opponent",
                            color="White" if is_white else "Black",
                            move_number=pending["move_number"],
                            played_move=pending["played_move"],
                            best_move=pending["best_move"],
                            eval_loss_cp=loss_cp,
                            mate_related=mate_related,
                            mate_in_before=mate_before,
                            mate_in_after=mate_after,
                        )
                    )

            for move in game.mainline_moves():
                info = engine.analyse(
                    board,
                    chess.engine.Limit(time=seconds_per_position),
                )

                # Evaluate the previous move using the new position.
                record_if_significant(info)

                score = info["score"].pov(board.turn)
                pv = info.get("pv", [])

                if not pv:
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

    # Mate-related blunders first, then ordinary centipawn losses.
    return sorted(
        mistakes,
        key=lambda mistake: (
            mistake.mate_related,
            mistake.eval_loss_cp or 0,
        ),
        reverse=True,
    )
