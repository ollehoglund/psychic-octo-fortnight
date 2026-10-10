# Lichess Game Analyzer

A Python CLI that fetches recent games from the Lichess API and summarizes your
results, colors, openings, and large evaluation drops in games with available
engine annotations. It uses `python-chess` to parse PGN; it does not run a chess
engine or create new evaluations.

## Install and run

```powershell
python -m pip install -e .
lichess-analyzer YOUR_USERNAME --max-games 30
```

You can also run it as a module:

```powershell
python -m lichess_analyzer YOUR_USERNAME
```

Public games can be fetched without a token. Create a `.env` file to avoid
passing your username on every command. The file is ignored by Git; never
commit or share it.

```dotenv
LICHESS_USERNAME=your_lichess_username
LICHESS_TOKEN=your_personal_access_token
```

Copy `.env.example` as a starting point and replace the placeholders in `.env`.
The token is optional for public games.

The analyzer requests PGN openings and evaluations where Lichess has them.
Evaluation-drop counts only include consecutive evaluated positions and flag
drops of at least 2.0 pawns from your perspective. Games without those
annotations are still included in the results and opening summaries.

## Test

```powershell
python -m unittest discover -s tests
```