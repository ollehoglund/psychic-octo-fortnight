
import os
import json

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from lichess_analyzer.analysis import analyze_pgn
from lichess_analyzer.storage import (
    get_games,
    get_saved_mistakes,
    initialize_database,
)
from sync_worker import run_sync

from lichess_analyzer.trends import trends_report


load_dotenv()
initialize_database()

st.set_page_config(
    page_title="Lichess Game Analyzer",
    page_icon="♟️",
    layout="wide",
)

st.title("♟️ Lichess Game Analyzer")
st.caption("Your personal chess improvement dashboard")


# -------------------------
# Sidebar settings
# -------------------------
with st.sidebar:
    st.header("Settings")

    username = st.text_input(
        "Lichess username",
        value=os.getenv("LICHESS_USERNAME", ""),
    ).strip()

    max_games = st.number_input(
        "Games to download",
        min_value=1,
        max_value=10000,
        value=40,
        step=10,
    )

    engine_time = st.number_input(
        "Stockfish time per position (seconds)",
        min_value=0.05,
        max_value=5.0,
        value=0.1,
        step=0.05,
    )

    st.divider()
    st.caption("Opening the dashboard does not run Stockfish.")

    sync_clicked = st.button(
        "Sync games and analyze",
        type="primary",
        use_container_width=True,
    )


if not username:
    st.info("Enter your Lichess username in the sidebar to continue.")
    st.stop()


# -------------------------
# Manual sync only
# -------------------------
if sync_clicked:
    try:
        with st.spinner(
            "Downloading games and analyzing games not yet cached..."
        ):
            run_sync(
                username=username,
                max_games=int(max_games),
                engine_time=float(engine_time),
            )

        st.success("Sync completed.")
    except Exception as exc:
        st.error(f"Sync failed: {exc}")

    st.rerun()


# -------------------------
# Load locally cached data
# -------------------------
games = get_games(username)
mistakes = get_saved_mistakes(username)

if not games:
    st.info(
        "No games are saved locally yet. Use 'Sync games and analyze' "
        "in the sidebar to download your games."
    )
    st.stop()


analyzed_count = sum(
    game.get("analysis_json") is not None for game in games
)

# -------------------------
# Overview metrics
# -------------------------
m1, m2, m3 = st.columns(3)

m1.metric("Games saved", len(games))
m2.metric("Games analyzed", analyzed_count)
m3.metric("Critical mistakes found", len(mistakes))

st.divider()


# -------------------------
# Tabs
# -------------------------
overview_tab, games_tab, mistakes_tab, trends_tab = st.tabs(
    [
        "📊 Overview",
        "♟️ Game history",
        "🔎 Stockfish findings",
        "📈 Trends & Training",
    ]
    )

# -------------------------
# Overview / readable summary
# -------------------------

with overview_tab:
    st.subheader("Your chess overview")

    cached_pgn = "\n\n".join(game["pgn"] for game in games)

    try:
        with st.spinner("Summarizing your saved games..."):
            report = analyze_pgn(cached_pgn, username)

        if not report.games:
            st.info(f"No games found for Lichess user '{username}'.")
        else:
            # Calculate statistics from the actual AnalysisReport.
            total = len(report.games)
            white_games = sum(g.color == "White" for g in report.games)
            black_games = total - white_games
            evaluated = sum(g.has_evaluations for g in report.games)
            eval_drops = sum(g.significant_eval_drops for g in report.games)

            st.markdown("### Your results")

            a, b, c, d = st.columns(4)
            a.metric("Wins", report.wins)
            b.metric("Draws", report.draws)
            c.metric("Losses", report.losses)
            d.metric("Score", f"{report.score_percentage:.1f}%")

            st.markdown("### Game analysis coverage")

            a, b, c = st.columns(3)
            a.metric("Played as White", white_games)
            b.metric("Played as Black", black_games)
            c.metric("Games with evaluations", f"{evaluated}/{total}")

            st.metric(
                "Large evaluation drops",
                eval_drops,
                help=(
                    "Counts 2-pawn-or-larger drops detected from evaluations "
                    "already embedded in the PGN. This is not a fresh Stockfish analysis."
                ),
            )

            st.markdown("### Most common openings")

            from collections import Counter

            opening_counts = Counter(
                g.opening for g in report.games
                if g.opening and g.opening != "Unknown opening"
            )

            if opening_counts:
                opening_rows = [
                    {"Opening": opening, "Games": count}
                    for opening, count in opening_counts.most_common(5)
                ]
                st.dataframe(
                    pd.DataFrame(opening_rows),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.caption("Opening names were not available in the saved games.")

            st.markdown("### Recent games")

            recent_rows = [
                {
                    "Date": g.date,
                    "Opponent": g.opponent,
                    "Color": g.color,
                    "Result": {
                        "W": "Win",
                        "D": "Draw",
                        "L": "Loss",
                        "?": "Unknown",
                    }.get(g.result, g.result),
                    "Opening": g.opening,
                    "Moves": (g.plies + 1) // 2,
                    "PGN evaluations": "Yes" if g.has_evaluations else "No",
                    "Large drops": g.significant_eval_drops,
                }
                for g in report.games[:10]
            ]

            st.dataframe(
                pd.DataFrame(recent_rows),
                use_container_width=True,
                hide_index=True,
            )

    except Exception as exc:
        st.warning(f"Couldn't build the game summary: {exc}")

    st.caption(
        "This report is calculated from cached PGNs and does not run Stockfish."
    )


# -------------------------
# Game history
# -------------------------
with games_tab:
    st.subheader("Locally saved games")

    game_rows = []

    for game in games:
        game_rows.append({
            "Date": game.get("date") or "Unknown",
            "Opponent": game.get("opponent") or "Unknown",
            "Result": game.get("result") or "Unknown",
            "Stockfish analysis": (
                "Complete"
                if game.get("analysis_json") is not None
                else "Pending"
            ),
        })

    game_df = pd.DataFrame(game_rows)

    st.dataframe(
        game_df,
        use_container_width=True,
        hide_index=True,
    )


# -------------------------
# Stockfish findings
# -------------------------
with mistakes_tab:
    st.subheader("Moves worth reviewing")

    if not mistakes:
        st.info(
            "No saved Stockfish findings yet. Use the sync button to "
            "analyze games that have not been analyzed."
        )
    else:
        df = pd.DataFrame(mistakes)

        # Rename known fields for display.
        rename_map = {
            "eval_loss_cp": "Evaluation loss (centipawns)",
            "game_date": "Date",
            "opponent": "Opponent",
            "move_number": "Move number",
            "san": "Move played",
            "played_move": "Move played",
            "best_move": "Engine suggestion",
            "fen": "Position",
            "mate_related": "Mate-related blunder",
            "mate_in_before": "Mate score before",
            "mate_in_after": "Mate score after",
        }

        df = df.rename(columns={
            old: new
            for old, new in rename_map.items()
            if old in df.columns
        })

        # Keep the table readable by putting the most significant
        # evaluation losses first, when that field is available.
        loss_column = "Evaluation loss (centipawns)"
        if loss_column in df.columns:
            df = df.sort_values(
                loss_column,
                ascending=False,
                na_position="last",
            )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "Centipawn losses are engine estimates, not percentages. "
            "Positions involving forced mates may need special interpretation."
        )

# -------------------------
# Trends and training
# -------------------------
with trends_tab:
    st.subheader("Your chess trends")
    st.caption(
        "These trends use saved game summaries and saved Stockfish findings. "
        "They do not run a new engine analysis."
    )

    report = analyze_pgn(
        "\n\n".join(game["pgn"] for game in games),
        username,
    )

    trends = trends_report(report, mistakes)

    st.markdown("### Performance by color")

    color_cols = st.columns(2)
    for col, color in zip(color_cols, ("White", "Black")):
        stats = trends["by_color"][color]
        with col:
            st.markdown(f"#### {color}")
            st.metric("Games", stats["games"])
            if stats["score_pct"] is not None:
                st.metric("Score", f"{stats['score_pct']:.1f}%")
                st.caption(
                    f"{stats['wins']} wins · {stats['draws']} draws · "
                    f"{stats['losses']} losses"
                )
            else:
                st.caption("Not enough completed results yet.")


    # -------------------------
    # Recent vs older games
    # -------------------------
    st.markdown("### Are you improving over time?")

    periods = trends["period_comparison"]
    older = periods["Older games"]
    recent = periods["Recent games"]

    if older["games"] and recent["games"]:
        st.caption(
            f"Older: {older['first_date']} to {older['last_date']} "
            f"({older['games']} games) · "
            f"Recent: {recent['first_date']} to {recent['last_date']} "
            f"({recent['games']} games)"
        )

        left, right = st.columns(2)

        with left:
            st.markdown("#### Older games")
            st.metric(
                "Score",
                f"{older['score_pct']:.1f}%"
                if older["score_pct"] is not None else "N/A",
            )
            st.metric(
                "Critical mistakes per 100 moves",
                f"{older['mistakes_per_100_moves']:.2f}"
                if older["mistakes_per_100_moves"] is not None else "N/A",
            )
            st.caption(
                f"{older['critical_mistakes']} saved critical findings "
                f"across {older['own_moves']} estimated moves."
            )

        with right:
            st.markdown("#### Recent games")
            st.metric(
                "Score",
                f"{recent['score_pct']:.1f}%"
                if recent["score_pct"] is not None else "N/A",
            )
            st.metric(
                "Critical mistakes per 100 moves",
                f"{recent['mistakes_per_100_moves']:.2f}"
                if recent["mistakes_per_100_moves"] is not None else "N/A",
            )
            st.caption(
                f"{recent['critical_mistakes']} saved critical findings "
                f"across {recent['own_moves']} estimated moves."
            )
    else:
        st.info(
            "More dated games are needed to compare older and recent periods."
        )

    # -------------------------
    # Mistake rates by color
    # -------------------------
    st.markdown("### Mistake patterns: White vs Black")

    color_rows = []
    for color in ("White", "Black"):
        stats = trends["by_color"][color]
        color_rows.append({
            "Color": color,
            "Games": stats["games"],
            "Score %": (
                round(stats["score_pct"], 1)
                if stats["score_pct"] is not None else None
            ),
            "Critical findings": stats["critical_mistakes"],
            "Findings per 100 moves": (
                round(stats["mistakes_per_100_moves"], 2)
                if stats["mistakes_per_100_moves"] is not None else None
            ),
            "Combined CP loss (pawns)": stats["combined_loss_pawns"],
        })

    st.dataframe(
        pd.DataFrame(color_rows),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "These rates count saved critical Stockfish findings, not every "
        "inaccuracy. Small samples can make color differences misleading."
    )

    # -------------------------
    # Long-term trends
    # -------------------------
    st.markdown("### Long-term progress")

    monthly_rows = trends["monthly"]
    if monthly_rows:
        monthly_df = pd.DataFrame(monthly_rows).set_index("Month")

        st.markdown("#### Score by month")
        st.line_chart(monthly_df[["Score %"]])

        st.markdown("#### Critical findings per 100 moves")
        st.line_chart(monthly_df[["Mistakes per 100 moves"]])

        with st.expander("View monthly data"):
            st.dataframe(
                monthly_df.reset_index(),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info(
            "No usable game dates were found for a monthly trend. "
            "Check whether your saved PGNs contain valid dates."
        )

    opening_rows = trends["openings"]
    if opening_rows:
        st.dataframe(
            pd.DataFrame(opening_rows),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            "Openings with fewer than five games are preliminary. "
            "Results depend on opponent strength and time control."
        )
    else:
        st.info(
            "Opening names are missing from your PGNs. "
            "Sync more games with opening headers to build this report."
        )

    st.markdown("### When do critical mistakes happen?")

    phase_df = pd.DataFrame(trends["phases"])
    st.dataframe(
        phase_df,
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Phases are approximated by move number, not by the actual "
        "material or strategic stage of the position. These are saved "
        "critical mistakes, not all errors in your games."
    )

    st.markdown("### Biggest saved mistakes")

    biggest = trends["biggest_mistakes"]
    if biggest:
        mistake_rows = []
        for mistake in biggest:
            mistake_rows.append({
                "Date": mistake.get("date", ""),
                "Opponent": mistake.get("opponent", ""),
                "Move": mistake.get("move_number", ""),
                "Your move": mistake.get("played_move", ""),
                "Engine suggestion": mistake.get("best_move", ""),
                "Evaluation loss (pawns)": 
                    (
                    round(int(mistake["eval_loss_cp"]) / 100, 2)
                    if mistake.get("eval_loss_cp") is not None
                    else None
                    ),
                "Mate-related": "Yes" if mistake.get("mate_related") else "No",
                "Mate before (signed)": mistake.get("mate_in_before"),
                "Mate after (signed)": mistake.get("mate_in_after"),
            })

        st.dataframe(
            pd.DataFrame(mistake_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "No saved critical mistakes yet. Run the manual sync to "
            "analyze games that have not been analyzed."
        )

    st.markdown("### Training priorities")

    for index, priority in enumerate(trends["priorities"], start=1):
        st.markdown(f"**{index}.** {priority}")
    

st.divider()
st.caption(
    "Your dashboard reads from the local SQLite database. "
    "Downloading games and running Stockfish happen only when you "
    "manually sync."
)
