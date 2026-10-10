"""Small standard-library client for the Lichess game export API."""

from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class LichessAPIError(RuntimeError):
    """Raised when Lichess cannot provide the requested game export."""


def fetch_user_games(
    username: str,
    max_games: int = 20,
    token: str | None = None,
) -> str:
    """Fetch a user's recent games as PGN text."""
    username = username.strip()
    if not username:
        raise ValueError("Lichess username must not be empty")
    if max_games < 1:
        raise ValueError("max_games must be at least 1")

    query = urlencode({"max": max_games, "opening": "true", "evals": "true"})
    url = f"https://lichess.org/api/games/user/{quote(username, safe='')}?{query}"
    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "lichess-game-analyzer/0.1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as error:
        if error.code == 429:
            message = "Lichess rate limit reached; wait before trying again"
        else:
            message = f"Lichess returned HTTP {error.code} for user {username!r}"
        raise LichessAPIError(message) from error
    except URLError as error:
        raise LichessAPIError(f"Could not reach Lichess: {error.reason}") from error
    except UnicodeDecodeError as error:
        raise LichessAPIError("Lichess returned a response that was not valid UTF-8") from error