# Lichess Game Analyzer

A modern chess analysis dashboard for reviewing your Lichess games, spotting repeated mistakes, and understanding how your opening repertoire and decision quality evolve over time.

## Overview

This project turns a Lichess account into a personal analysis website: it downloads your recent games, stores them locally, summarizes key performance trends, and highlights critical mistakes using engine-backed evaluations when available.

The app is built as a Streamlit dashboard for daily use, with a command-line companion for quicker batch analysis.

## Why this project

Chess improvement is not just about winning games. It is about finding patterns in:

- your opening choices
- the positions where your evaluation drops sharply
- recurring tactical mistakes
- how often your games contain engine-evaluated positions
- your overall results by color, opening, and recent performance

This analyzer brings those insights together in one place so you can study your games more intentionally.

## Features

- Download and cache recent public Lichess games
- Analyze game outcomes, colors, openings, and move counts
- Detect large evaluation drops from PGN annotations
- Run deeper Stockfish checks for significant positions
- View a clean dashboard with overview metrics and game history
- Keep a local database so repeated analysis is fast
- Works both as a website and as a Python CLI

## Live dashboard

Start the website locally:

```powershell
python -m pip install -e .
streamlit run app.py
```

Then open the local Streamlit URL in your browser and use the sidebar to:

- enter your Lichess username
- choose how many games to sync
- set Stockfish evaluation time per position
- trigger a refresh of cached game analysis

## Quick start

### 1. Install dependencies

```powershell
python -m pip install -e .
```

### 2. Add your environment variables

Create a `.env` file in the project root:

```dotenv
LICHESS_USERNAME=your_lichess_username
LICHESS_TOKEN=your_personal_access_token
STOCKFISH_PATH=C:/path/to/stockfish.exe
```

Notes:

- `LICHESS_USERNAME` is optional if you enter it in the app UI
- `LICHESS_TOKEN` is optional for public games but recommended for higher API limits
- `STOCKFISH_PATH` is required only when running engine analysis
- `.env` should stay local and should not be committed

### 3. Run the CLI

```powershell
lichess-analyzer YOUR_USERNAME --max-games 30
```

Or run as a module:

```powershell
python -m lichess_analyzer YOUR_USERNAME --max-games 30
```

## How the analysis works

The app does three main jobs:

1. Fetches recent games from the Lichess API
2. Parses those games and summarizes the results, openings, and evaluation data
3. Highlights notable mistakes or evaluation swings, especially with Stockfish when configured

The dashboard uses cached local data so you can revisit prior analyses quickly without re-downloading everything each time.

## Data model

The project keeps a local SQLite database that stores:

- game metadata
- PGN text
- cached analysis summaries
- mistakes detected from Stockfish findings

This makes the dashboard responsive and avoids repeated network calls on every load.

## Development

Run the test suite:

```powershell
python -m unittest discover -s tests
```

## Project structure

```text
psychic-octo-fortnight/
├── app.py                    # Streamlit dashboard
├── sync_worker.py            # sync and analysis orchestration
├── lichess_analyzer/        # package logic
│   ├── analysis.py
│   ├── cli.py
│   ├── client.py
│   ├── engine_analysis.py
│   └── storage.py
├── tests/                   # project tests
├── pyproject.toml           # package metadata
├── .env                     # local env file (not committed)
└── README.md                # project documentation
```

## Example workflow

- Open the dashboard
- Enter your username
- Sync your most recent games
- Review overview metrics and trends
- Inspect game history and critical mistakes
- Use the engine findings to focus your next training sessions

## License

This project is developed for personal chess improvement analysis and is intended for local use and experimentation.

## Contributing

If you want to extend the app, you could add features like:

- player trend charts over time
- opening-specific statistics
- deeper puzzle-style analysis
- move-by-move interactive review
- exportable reports and CSV summaries

---

Built for studying your chess, one game at a time.