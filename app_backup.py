
"""Local Streamlit dashboard for Lichess game analysis."""

from __future__ import annotations

import os
from dataclasses import asdict

import pandas as pd
import streamlit as st
import chess.engine
from dotenv import load_dotenv

from lichess_analyzer.analysis import analyze_pgn
from lichess_analyzer.client import fetch_user_games, LichessAPIError
from lichess_analyzer.engine_analysis import analyze_games_with_engine

from lichess_analyzer.storage import (
    get_games,
    get_saved_mistakes,
    initialize_database,
)


load_dotenv()

st.set_page_config(
    page_title="Lichess Chess Coach",
    page_icon="♟️",
    layout="wide",
)

st.title("♟️ Lichess Chess Coach")
st.caption("Your games, Stockfish analysis, and practical improvement insights.")

default_username = os.environ.get("LICHESS_USERNAME", "")
default_engine = os.environ.get("STOCKFISH_PATH", "")

with st.sidebar:
    st.header("Settings")
    username = st.text_input("Lichess username", value=default_username)
    max_games = st.number_input(
        "Games to download",
        min_value=1,
        max_value=500,
        value=40,
        step=10,
    )
    engine_path = st.text_input("Stockfish executable", value=default_engine)
    engine_time = st.select_slider(
        "Engine time per position",
        options=[0.1, 0.2, 0.5, 1.0],
        value=0.2,
    )

    sync_clicked = st.button(
        "🔄 Sync games",
        type="primary",
        use_container_width=True,
    )
    engine_clicked = st.button(
        "🧠 Run Stockfish analysis",
        use_container_width=True,
    )

if sync_clicked:
    if not username.strip():
        st.error("Enter your Lichess username in the sidebar.")
    else:
        try:
            with st.spinner("Downloading games from Lichess..."):
                pgn = fetch_user_games(
                    username.strip(),
                    max_games=int(max_games),
                    token=os.environ.get("LICHESS_TOKEN"),
                )
                report = analyze_pgn(pgn, username.strip())

            st.session_state["pgn"] = pgn
            st.session_state["report"] = report
            st.session_state["username"] = username.strip()
            st.session_state.pop("mistakes", None)
            st.success(f"Loaded {len(report.games)} games.")
        except (LichessAPIError, ValueError, OSError) as error:
            st.error(f"Could not load games: {error}")

report = st.session_state.get("report")
pgn = st.session_state.get("pgn")

if report is None:
    st.info(
        "Choose your settings and click **Sync games** to load your "
        "recent Lichess games."
    )
    st.stop()

st.subheader(f"Performance overview — {report.username}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Games", len(report.games))
col2.metric("Wins", report.wins)
col3.metric("Draws", report.draws)
col4.metric("Losses", report.losses)

st.metric("Score percentage", f"{report.score_percentage:.1f}%")

games_data = [asdict(game) for game in report.games]
games_df = pd.DataFrame(games_data)

tab_overview, tab_games, tab_coach = st.tabs(
    ["📊 Overview", "♟️ Games", "🎯 Coaching"]
)

with tab_overview:
    left, right = st.columns(2)

    with left:
        st.markdown("#### Results")
        results_df = pd.DataFrame(
            {
                "Result": ["Wins", "Draws", "Losses"],
                "Games": [report.wins, report.draws, report.losses],
            }
        ).set_index("Result")
        st.bar_chart(results_df)

    with right:
        st.markdown("#### Most-played openings")
        if "opening" in games_df.columns:
            openings = (
                games_df["opening"]
                .fillna("Unknown")
                .replace("", "Unknown")
                .value_counts()
                .head(10)
            )
            st.bar_chart(openings)
        else:
            st.write("Opening information isn't available.")

    st.markdown("#### Analysis coverage")
    evaluated = sum(game.has_evaluations for game in report.games)
    st.write(f"Games containing evaluations: {evaluated} of {len(report.games)}")

    drops = sum(game.significant_eval_drops for game in report.games)
    st.write(f"Large evaluation drops in imported PGNs: {drops}")

with tab_games:
    st.markdown("#### Recent games")
    st.dataframe(
        games_df,
        use_container_width=True,
        hide_index=True,
    )

with tab_coach:
    st.markdown("#### Your next training priorities")

    total = len(report.games)
    if total:
        white_games = sum(game.color.lower() == "white" for game in report.games)
        black_games = total - white_games

        st.write(
            f"You have {total} games in this report: "
            f"{white_games} as White and {black_games} as Black."
        )

        if report.score_percentage >= 60:
            st.success(
                "Your score in this sample is strong. Review losses to find "
                "recurring mistakes rather than focusing only on wins."
            )
        elif report.score_percentage >= 45:
            st.info(
                "Your results are around the middle range. Look for repeated "
                "tactical errors and compare your opening results."
            )
        else:
            st.info(
                "Start by reviewing decisive losses. Focus on hanging pieces, "
                "king safety, and missed opponent threats."
            )

    st.caption(
        "These are preliminary suggestions based on results, not a full "
        "positional diagnosis. Stockfish analysis provides more specific evidence."
    )

    if engine_clicked:
        if not engine_path.strip():
            st.error("Set the Stockfish executable path in the sidebar.")
        elif not os.path.isfile(engine_path.strip()):
            st.error("The Stockfish executable was not found at that path.")
        else:
            try:
                progress = st.progress(0, text="Starting Stockfish...")
                status = st.empty()

                with st.spinner("Analyzing game positions. This can take a while..."):
                    mistakes = analyze_games_with_engine(
                        pgn,
                        report.username,
                        engine_path.strip(),
                        seconds_per_position=float(engine_time),
                    )

                st.session_state["mistakes"] = [
                    asdict(mistake) for mistake in mistakes
                ]
                progress.progress(100, text="Analysis complete")
                status.success("Stockfish analysis finished.")
            except (chess.engine.EngineError, OSError, ValueError) as error:
                st.error(f"Stockfish analysis failed: {error}")

    mistakes = st.session_state.get("mistakes")
    if mistakes is not None:
        st.markdown("#### Biggest potential mistakes")
        if not mistakes:
            st.success("No moves crossed the configured 2-pawn loss threshold.")
        else:
            mistakes_df = pd.DataFrame(mistakes)
            mistakes_df["Estimated loss (pawns)"] = (
                mistakes_df["eval_loss_cp"] / 100
            )
            st.dataframe(
                mistakes_df[
                    [
                        "date",
                        "opponent",
                        "color",
                        "move_number",
                        "played_move",
                        "best_move",
                        "Estimated loss (pawns)",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.warning(
                "Mate-score handling in the current engine module still needs "
                "correction, so extreme loss values may be misleading."
            )
