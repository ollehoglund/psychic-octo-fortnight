
"""Paginated client for the Lichess game export API."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class LichessAPIError(RuntimeError):
    """Raised when Lichess cannot provide the requested game export."""


PAGE_SIZE = 300
REQUEST_PAUSE_SECONDS = 1.0


def _split_pgn_games(pgn_text: str) -> list[str]:
    """Split an exported PGN into individual games."""
    if not pgn_text.strip():
        return []

    parts = re.split(r"(?=^\[Event\s)", pgn_text, flags=re.MULTILINE)
    return [
        part.strip()
        for part in parts
        if part.strip() and re.search(r"^\[Event\s", part, re.MULTILINE)
    ]


def _is_standard_chess(pgn: str) -> bool:
    """Return True only for standard chess PGNs."""
    match = re.search(
        r'^\[Variant\s+"([^"]+)"\]',
        pgn,
        re.MULTILINE | re.IGNORECASE,
    )

    # Lichess standard chess PGNs generally omit the Variant header.
    return (
        match is None
        or match.group(1).strip().casefold() in {"standard", "chess"}
    )


def _game_timestamp_ms(pgn: str) -> int | None:
    """Read the game's UTC date/time headers as Unix milliseconds."""
    date_match = re.search(
        r'^\[UTCDate\s+"(\d{4})\.(\d{2})\.(\d{2})"\]',
        pgn,
        re.MULTILINE,
    )
    time_match = re.search(
        r'^\[UTCTime\s+"(\d{2}):(\d{2}):(\d{2})"\]',
        pgn,
        re.MULTILINE,
    )

    if not date_match or not time_match:
        return None

    try:
        value = (
            f"{date_match.group(1)}-{date_match.group(2)}-"
            f"{date_match.group(3)} "
            f"{time_match.group(1)}:{time_match.group(2)}:"
            f"{time_match.group(3)}"
        )
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def _fetch_page(
    username: str,
    limit: int,
    token: str | None,
    since_ms: int | None,
    opponent: str | None = None,
) -> str:
    params = {
        "max": min(limit, PAGE_SIZE),
        "opening": "true",
        "evals": "true",
        "sort": "dateDesc",
    }
    if opponent:
        params["vs"] = opponent.strip()

    if since_ms is not None:
        params["since"] = since_ms

    url = (
        f"https://lichess.org/api/games/user/"
        f"{quote(username, safe='')}?{urlencode(params)}"
    )

    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "lichess-game-analyzer/0.2",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, headers=headers)

    try:
        with urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8")
    except HTTPError as error:
        if error.code == 429:
            message = "Lichess rate limit reached; wait before trying again."
        else:
            message = (
                f"Lichess returned HTTP {error.code} "
                f"for user {username!r}."
            )
        raise LichessAPIError(message) from error
    except URLError as error:
        raise LichessAPIError(
            f"Could not reach Lichess: {error.reason}"
        ) from error
    except UnicodeDecodeError as error:
        raise LichessAPIError(
            "Lichess returned invalid UTF-8."
        ) from error

def fetch_user_games(
    username: str,
    max_games: int = 20,
    token: str | None = None,
    opponent: str | None = None,
) -> str:
    """Fetch up to max_games standard chess games, oldest first."""
    username = username.strip()

    if not username:
        raise ValueError("Lichess username must not be empty")
    if max_games < 1:
        raise ValueError("max_games must be at least 1")

    collected: list[str] = []
    since_ms = None
    seen_timestamps = set()

    while len(collected) < max_games:
        remaining = max_games - len(collected)
        page_limit = min(max(remaining, 300), PAGE_SIZE)

        if collected:
            time.sleep(REQUEST_PAUSE_SECONDS)

        print(
            f"Fetching page: {len(collected)} of "
            f"{max_games} standard games collected..."
        )

        response = _fetch_page(
            username,
            page_limit,
            token,
            since_ms,
            opponent=opponent,
        )

        page_games = _split_pgn_games(response)

        if not page_games:
            break

        standard_games = [
            game for game in page_games
            if _is_standard_chess(game)
        ]

        collected.extend(standard_games[:remaining])

        timestamps = [
            _game_timestamp_ms(game)
            for game in page_games
        ]
        valid_timestamps = [ts for ts in timestamps if ts is not None]

        # If the API returned fewer games than requested, history is exhausted.
        if len(page_games) < page_limit:
            break

        if not valid_timestamps:
            raise LichessAPIError(
                "Cannot paginate safely because the returned games "
                "do not contain valid UTCDate and UTCTime headers."
            )

        last_timestamp = max(valid_timestamps)

        if last_timestamp in seen_timestamps:
            raise LichessAPIError(
                "Pagination did not advance. Stopping to avoid "
                "repeatedly downloading the same page."
            )

        seen_timestamps.add(last_timestamp)
        since_ms = last_timestamp + 1

    return "\n\n".join(collected[:max_games]) + (
        "\n\n" if collected else ""
    )
