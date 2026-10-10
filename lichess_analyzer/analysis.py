"""Parse exported PGNs and summarize results and available evaluations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from io import StringIO

import chess
import chess.pgn


SIGNIFICANT_EVAL_DROP_CP = 200


@dataclass(frozen=True)
class GameSummary:
    date: str
    opponent: str
    color: str
    result: str
    opening: str
    plies: int
    has_evaluations: bool
    significant_eval_drops: int


@dataclass(frozen=True)
class AnalysisReport:
    username: str
    games: tuple[GameSummary, ...]

    @property
    def wins(self) -> int:
        return sum(game.result == "W" for game in self.games)

    @property
    def draws(self) -> int:
        return sum(game.result == "D" for game in self.games)

    @property
    def losses(self) -> int:
        return sum(game.result == "L" for game in self.games)

    @property
    def score_percentage(self) -> float:
        if not self.games:
            return 0.0
        points = self.wins + 0.5 * self.draws
        return 100 * points / len(self.games)


def _result_for_user(result: str, user_is_white: bool) -> str:
    if result == "1/2-1/2":
        return "D"
    if result == "1-0":
        return "W" if user_is_white else "L"
    if result == "0-1":
        return "L" if user_is_white else "W"
    return "?"


def _count_eval_drops(game: chess.pgn.Game, user_color: chess.Color) -> tuple[bool, int]:
    previous_white_score: int | None = None
    has_evaluations = False
    significant_drops = 0

    for node in game.mainline():
        evaluation = node.eval()
        if evaluation is None:
            previous_white_score = None
            continue

        white_score = evaluation.pov(chess.WHITE).score(mate_score=10_000)
        if white_score is None:
            previous_white_score = None
            continue

        has_evaluations = True
        if previous_white_score is not None and node.parent is not None:
            mover = node.parent.board().turn
            change_for_mover = (
                white_score - previous_white_score
                if mover == chess.WHITE
                else previous_white_score - white_score
            )
            if mover == user_color and change_for_mover <= -SIGNIFICANT_EVAL_DROP_CP:
                significant_drops += 1

        previous_white_score = white_score

    return has_evaluations, significant_drops


def analyze_pgn(pgn_text: str, username: str) -> AnalysisReport:
    """Summarize the user's games and large eval drops where evals exist."""
    username = username.strip()
    if not username:
        raise ValueError("Lichess username must not be empty")

    summaries: list[GameSummary] = []
    stream = StringIO(pgn_text)
    while game := chess.pgn.read_game(stream):
        if game.errors:
            raise ValueError(f"Could not parse PGN game: {game.errors[0]}")

        headers = game.headers
        white_name = headers.get("White", "")
        black_name = headers.get("Black", "")
        user_is_white = white_name.casefold() == username.casefold()
        user_is_black = black_name.casefold() == username.casefold()
        if not user_is_white and not user_is_black:
            continue

        user_color = chess.WHITE if user_is_white else chess.BLACK
        opponent = black_name if user_is_white else white_name
        has_evaluations, eval_drops = _count_eval_drops(game, user_color)
        summaries.append(
            GameSummary(
                date=headers.get("UTCDate", headers.get("Date", "Unknown date")),
                opponent=opponent or "Unknown opponent",
                color="White" if user_is_white else "Black",
                result=_result_for_user(headers.get("Result", "*"), user_is_white),
                opening=headers.get("Opening", "Unknown opening"),
                plies=sum(1 for _ in game.mainline_moves()),
                has_evaluations=has_evaluations,
                significant_eval_drops=eval_drops,
            )
        )

    return AnalysisReport(username=username, games=tuple(summaries))


def render_report(report: AnalysisReport) -> str:
    """Format an analysis report for terminal output."""
    if not report.games:
        return f"No games found for {report.username!r}."

    white_games = sum(game.color == "White" for game in report.games)
    black_games = len(report.games) - white_games
    evaluated_games = sum(game.has_evaluations for game in report.games)
    eval_drops = sum(game.significant_eval_drops for game in report.games)
    openings = Counter(game.opening for game in report.games)

    lines = [
        f"Lichess game report: {report.username}",
        f"Games: {len(report.games)} | Record: {report.wins}-{report.draws}-{report.losses}",
        f"Score: {report.score_percentage:.1f}% | White: {white_games} | Black: {black_games}",
        f"Games with evaluations: {evaluated_games}/{len(report.games)}",
        f"Large evaluation drops (2.0+ pawns): {eval_drops}",
        "Most common openings:",
    ]
    for opening, count in openings.most_common(5):
        lines.append(f"  {opening}: {count}")

    lines.append("Recent games:")
    for game in report.games[:10]:
        lines.append(
            f"  {game.date} | {game.result} as {game.color} vs {game.opponent}"
            f" | {game.opening} | {game.plies} plies"
        )

    return "\n".join(lines)