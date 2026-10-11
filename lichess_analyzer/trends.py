
"""Trend calculations for the Lichess dashboard."""

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime


PHASES = (
    "Opening (moves 1–10)",
    "Middlegame (moves 11–25)",
    "Endgame / late game (move 26+)",
)


def result_points(result):
    return {"W": 1.0, "D": 0.5, "L": 0.0}.get(result)


def parse_date(value):
    """Parse common PGN and ISO date formats."""
    if not value:
        return None

    value = str(value).strip()
    if not value or value in {"?", "Unknown", "None"}:
        return None

    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def score_stats(games):
    games = list(games)
    scored = [g for g in games if result_points(g.result) is not None]

    points = sum(result_points(g.result) for g in scored)

    return {
        "games": len(games),
        "scored_games": len(scored),
        "wins": sum(g.result == "W" for g in scored),
        "draws": sum(g.result == "D" for g in scored),
        "losses": sum(g.result == "L" for g in scored),
        "score_pct": 100 * points / len(scored) if scored else None,
    }


def _mistake_date(mistake):
    return parse_date(
        mistake.get("date") or mistake.get("game_date")
    )


def _game_date(game):
    return parse_date(getattr(game, "date", None))


def _color(value):
    value = str(value or "").strip().lower()
    if value in {"white", "w"}:
        return "White"
    if value in {"black", "b"}:
        return "Black"
    return None


def _own_moves(game):
    """Estimate the number of moves played by the account's side."""
    plies = max(0, int(getattr(game, "plies", 0) or 0))
    color = _color(getattr(game, "color", None))

    if color == "White":
        return (plies + 1) // 2
    if color == "Black":
        return plies // 2
    return plies / 2


def _game_key(date_value, opponent, color):
    parsed = parse_date(date_value)
    if parsed is None:
        return None

    return (
        parsed.isoformat(),
        str(opponent or "").strip().casefold(),
        _color(color),
    )


def _mistake_key(mistake):
    return _game_key(
        mistake.get("date") or mistake.get("game_date"),
        mistake.get("opponent"),
        mistake.get("color"),
    )


def _loss_cp(mistake):
    """Mate-related findings may not have a centipawn loss."""
    value = mistake.get("eval_loss_cp")
    try:
        return max(0, int(value)) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def trends_report(report, mistakes):
    games = list(report.games)
    mistakes = [
        asdict(m) if hasattr(m, "__dataclass_fields__") else dict(m)
        for m in mistakes
    ]

    # Match saved findings to games using date, opponent, and color.
    # Also keep a date-and-color fallback for incomplete opponent names.
    exact_game_keys = set()
    date_color_keys = set()

    for game in games:
        key = _game_key(
            getattr(game, "date", None),
            getattr(game, "opponent", None),
            getattr(game, "color", None),
        )
        if key:
            exact_game_keys.add(key)
            date_color_keys.add((key[0], key[2]))

    matched_mistakes = []
    for mistake in mistakes:
        key = _mistake_key(mistake)
        if key and (
            key in exact_game_keys
            or (key[0], key[2]) in date_color_keys
        ):
            matched_mistakes.append(mistake)

    # Performance by color.
    by_color = {}
    mistakes_by_color = Counter()
    moves_by_color = Counter()
    losses_by_color = Counter()

    for color in ("White", "Black"):
        color_games = [
            g for g in games if _color(g.color) == color
        ]
        stats = score_stats(color_games)

        own_moves = sum(_own_moves(g) for g in color_games)
        color_mistakes = [
            m for m in matched_mistakes
            if _color(m.get("color")) == color
        ]

        mistakes_by_color[color] = len(color_mistakes)
        moves_by_color[color] = own_moves
        losses_by_color[color] = sum(_loss_cp(m) for m in color_mistakes)

        stats.update({
            "own_moves": int(own_moves),
            "critical_mistakes": len(color_mistakes),
            "mistakes_per_100_moves": (
                100 * len(color_mistakes) / own_moves
                if own_moves else None
            ),
            "combined_loss_pawns": round(
                losses_by_color[color] / 100, 2
            ),
        })
        by_color[color] = stats

    # Opening performance by opening and color.
    opening_groups = defaultdict(list)
    for game in games:
        opening = getattr(game, "opening", None)
        if opening and opening != "Unknown opening":
            opening_groups[(opening, _color(game.color))].append(game)

    openings = []
    for (opening, color), group in opening_groups.items():
        stats = score_stats(group)
        openings.append({
            "Opening": opening,
            "Color": color or "Unknown",
            "Games": stats["scored_games"],
            "Wins": stats["wins"],
            "Draws": stats["draws"],
            "Losses": stats["losses"],
            "Score %": (
                round(stats["score_pct"], 1)
                if stats["score_pct"] is not None else None
            ),
        })

    openings.sort(
        key=lambda row: (
            row["Games"] < 3,
            row["Score %"] if row["Score %"] is not None else -1,
            row["Games"],
        ),
        reverse=True,
    )

    # Mistakes by approximate game phase.
    phase_counts = Counter()
    phase_loss = Counter()

    for mistake in matched_mistakes:
        move = int(mistake.get("move_number", 0) or 0)

        if move <= 10:
            phase = PHASES[0]
        elif move <= 25:
            phase = PHASES[1]
        else:
            phase = PHASES[2]

        phase_counts[phase] += 1
        phase_loss[phase] += _loss_cp(mistake)

    phase_rows = [
        {
            "Game phase": phase,
            "Critical mistakes": phase_counts[phase],
            "Combined CP loss (pawns)": round(
                phase_loss[phase] / 100, 2
            ),
        }
        for phase in PHASES
    ]

    # Compare older and newer halves of the dated game collection.
    dated_games = sorted(
        [g for g in games if _game_date(g)],
        key=_game_date,
    )
    midpoint = len(dated_games) // 2
    older_games = dated_games[:midpoint]
    recent_games = dated_games[midpoint:]

    def period_stats(period_games):
        keys = {
            _game_key(g.date, g.opponent, g.color)
            for g in period_games
        }
        keys.discard(None)

        period_mistakes = [
            m for m in matched_mistakes
            if _mistake_key(m) in keys
        ]
        own_moves = sum(_own_moves(g) for g in period_games)
        stats = score_stats(period_games)

        stats.update({
            "first_date": (
                _game_date(period_games[0]).isoformat()
                if period_games else None
            ),
            "last_date": (
                _game_date(period_games[-1]).isoformat()
                if period_games else None
            ),
            "own_moves": int(own_moves),
            "critical_mistakes": len(period_mistakes),
            "mistakes_per_100_moves": (
                100 * len(period_mistakes) / own_moves
                if own_moves else None
            ),
            "combined_loss_pawns": round(
                sum(_loss_cp(m) for m in period_mistakes) / 100, 2
            ),
        })
        return stats

    period_comparison = {
        "Older games": period_stats(older_games),
        "Recent games": period_stats(recent_games),
    }

    # Monthly long-term trends. Each month's mistake rate is normalized
    # by the estimated number of moves played by the account.
    monthly = defaultdict(
        lambda: {"games": 0, "points": 0.0, "scored": 0, "own_moves": 0}
    )
    for game in games:
        day = _game_date(game)
        if day is None:
            continue

        month = day.strftime("%Y-%m")
        row = monthly[month]
        row["games"] += 1
        row["own_moves"] += _own_moves(game)

        points = result_points(game.result)
        if points is not None:
            row["points"] += points
            row["scored"] += 1

    monthly_mistakes = Counter()
    for mistake in matched_mistakes:
        day = _mistake_date(mistake)
        if day:
            monthly_mistakes[day.strftime("%Y-%m")] += 1

    monthly_rows = []
    for month in sorted(monthly):
        row = monthly[month]
        monthly_rows.append({
            "Month": month,
            "Games": row["games"],
            "Score %": (
                round(100 * row["points"] / row["scored"], 1)
                if row["scored"] else None
            ),
            "Critical mistakes": monthly_mistakes[month],
            "Mistakes per 100 moves": (
                round(
                    100 * monthly_mistakes[month] / row["own_moves"], 2
                )
                if row["own_moves"] else None
            ),
        })

    # Representative examples: keep actual saved move data, including
    # FEN when available, for later position review.
    biggest = sorted(
        matched_mistakes,
        key=lambda m: (
            bool(m.get("mate_related")),
            _loss_cp(m),
        ),
        reverse=True,
    )[:10]

    examples_by_phase = {}
    for phase in PHASES:
        phase_examples = [
            m for m in matched_mistakes
            if (
                (int(m.get("move_number", 0) or 0) <= 10
                 and phase == PHASES[0])
                or (11 <= int(m.get("move_number", 0) or 0) <= 25
                    and phase == PHASES[1])
                or (int(m.get("move_number", 0) or 0) >= 26
                    and phase == PHASES[2])
            )
        ]
        examples_by_phase[phase] = sorted(
            phase_examples,
            key=lambda m: (bool(m.get("mate_related")), _loss_cp(m)),
            reverse=True,
        )[:3]

    # Data-based priorities only; these are not tactical diagnoses.
    priorities = []
    if matched_mistakes:
        phase, count = phase_counts.most_common(1)[0]
        priorities.append(
            f"{phase} has the most saved critical findings ({count}). "
            "Review the examples before concluding why the mistakes occurred."
        )

    older_rate = period_comparison["Older games"]["mistakes_per_100_moves"]
    recent_rate = period_comparison["Recent games"]["mistakes_per_100_moves"]
    if older_rate is not None and recent_rate is not None:
        if recent_rate < older_rate:
            priorities.append(
                f"Your saved critical-mistake rate improved from "
                f"{older_rate:.2f} to {recent_rate:.2f} per 100 moves."
            )
        elif recent_rate > older_rate:
            priorities.append(
                f"Your saved critical-mistake rate rose from "
                f"{older_rate:.2f} to {recent_rate:.2f} per 100 moves. "
                "Review recent examples to look for a recurring pattern."
            )
        else:
            priorities.append(
                "Your saved critical-mistake rate is similar in both periods."
            )

    for color, stats in by_color.items():
        if stats["scored_games"] >= 5 and stats["score_pct"] is not None:
            priorities.append(
                f"As {color.lower()}, your score is {stats['score_pct']:.1f}% "
                f"across {stats['scored_games']} games with known results."
            )

    if not priorities:
        priorities.append(
            "Sync and analyze more games to build reliable comparisons. "
            "Rates are based on saved critical findings, not every mistake."
        )

    return {
        "by_color": by_color,
        "openings": openings,
        "phases": phase_rows,
        "biggest_mistakes": biggest,
        "priorities": priorities,
        "period_comparison": period_comparison,
        "monthly": monthly_rows,
        "examples_by_phase": examples_by_phase,
        "matched_mistakes": matched_mistakes,
    }
