import os
import unittest
from unittest.mock import patch

from lichess_analyzer import cli


class CliConfigurationTests(unittest.TestCase):
    def test_uses_username_from_environment_when_argument_is_omitted(self) -> None:
        with (
            patch("sys.argv", ["lichess-analyzer"]),
            patch.dict(os.environ, {"LICHESS_USERNAME": "Alice", "LICHESS_TOKEN": "test-token"}),
            patch.object(cli, "load_dotenv"),
            patch.object(cli, "fetch_user_games", return_value="") as fetch,
            patch.object(cli, "analyze_pgn", return_value=object()),
            patch.object(cli, "render_report", return_value="report"),
            patch("builtins.print"),
        ):
            result = cli.main()

        self.assertEqual(result, 0)
        fetch.assert_called_once_with("Alice", max_games=20, token="test-token")


if __name__ == "__main__":
    unittest.main()