
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
        max_value=500,
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
overview_tab, games_tab, mistakes_tab = st.tabs(
    ["📊 Overview", "♟️ Game history", "🔎 Stockfish findings"]
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


st.divider()
st.caption(
    "Your dashboard reads from the local SQLite database. "
    "Downloading games and running Stockfish happen only when you "
    "manually sync."
)
