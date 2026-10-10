import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from lichess_analyzer.client import LichessAPIError, fetch_user_games


class LichessClientTests(unittest.TestCase):
    def test_requests_pgn_with_eval_and_opening_data(self) -> None:
        with patch("lichess_analyzer.client.urlopen", return_value=io.BytesIO(b"[Event \"test\"]")) as urlopen:
            pgn = fetch_user_games("Alice", max_games=7)

        request = urlopen.call_args.args[0]
        self.assertEqual(pgn, '[Event "test"]')
        self.assertIn("/api/games/user/Alice?", request.full_url)
        self.assertIn("max=7", request.full_url)
        self.assertIn("opening=true", request.full_url)
        self.assertIn("evals=true", request.full_url)
        self.assertEqual(request.get_header("Accept"), "application/x-chess-pgn")

    def test_adds_optional_bearer_token_as_a_header(self) -> None:
        with patch("lichess_analyzer.client.urlopen", return_value=io.BytesIO(b"")) as urlopen:
            fetch_user_games("Alice", token="secret-token")

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertNotIn("secret-token", request.full_url)

    def test_reports_rate_limit_without_retrying(self) -> None:
        error = HTTPError("https://lichess.org", 429, "Too Many Requests", None, io.BytesIO())
        with patch("lichess_analyzer.client.urlopen", side_effect=error):
            with self.assertRaisesRegex(LichessAPIError, "rate limit"):
                fetch_user_games("Alice")

    def test_rejects_empty_username_and_invalid_limit(self) -> None:
        with self.assertRaises(ValueError):
            fetch_user_games(" ")
        with self.assertRaises(ValueError):
            fetch_user_games("Alice", max_games=0)


if __name__ == "__main__":
    unittest.main()