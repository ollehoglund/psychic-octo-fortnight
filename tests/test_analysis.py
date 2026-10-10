import unittest

from lichess_analyzer.analysis import analyze_pgn, render_report


PGN = '''[Event "rated blitz game"]
[Site "https://lichess.org/example1"]
[UTCDate "2026.10.01"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]
[Opening "Italian Game"]

1. e4 {[%eval 0.20]} e5 {[%eval 0.10]} 2. Nf3 {[%eval -2.20]} Nc6 {[%eval -2.10]} 3. Bc4 a6 1-0

[Event "rated rapid game"]
[UTCDate "2026.10.02"]
[White "Carol"]
[Black "alice"]
[Result "1/2-1/2"]
[Opening "Sicilian Defense"]

1. e4 e5 2. Nf3 Nc6 1/2-1/2
'''


class GameAnalysisTests(unittest.TestCase):
    def test_summarizes_results_color_openings_and_eval_drops(self) -> None:
        report = analyze_pgn(PGN, "Alice")

        self.assertEqual(len(report.games), 2)
        self.assertEqual((report.wins, report.draws, report.losses), (1, 1, 0))
        self.assertEqual(report.score_percentage, 75.0)
        self.assertEqual(report.games[0].color, "White")
        self.assertEqual(report.games[0].significant_eval_drops, 1)
        self.assertFalse(report.games[1].has_evaluations)
        self.assertEqual(report.games[1].opponent, "Carol")

    def test_ignores_games_that_do_not_include_the_username(self) -> None:
        report = analyze_pgn(PGN, "SomeoneElse")

        self.assertEqual(report.games, ())
        self.assertIn("No games found", render_report(report))

    def test_rendered_report_explains_evaluation_coverage(self) -> None:
        report = analyze_pgn(PGN, "Alice")

        rendered = render_report(report)

        self.assertIn("Games with evaluations: 1/2", rendered)
        self.assertIn("Large evaluation drops (2.0+ pawns): 1", rendered)
        self.assertIn("Italian Game", rendered)

    def test_rejects_empty_username(self) -> None:
        with self.assertRaises(ValueError):
            analyze_pgn(PGN, " ")


if __name__ == "__main__":
    unittest.main()