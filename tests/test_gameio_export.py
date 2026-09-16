import unittest
from pathlib import Path

from reelgen.gameio import export_text, parse_file, parse_text, render_reelset

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"


class TestExport(unittest.TestCase):
    def setUp(self):
        self.game = parse_file(FIXTURE)

    def test_render_reelset_is_space_separated_lines(self):
        body = render_reelset([[1, 2, 3], [9, 9, 10]])
        self.assertEqual(body, "\n1 2 3\n9 9 10\n")

    def test_round_trip_without_changes_is_identical(self):
        out = export_text(self.game.source_text, self.game.reelsets)
        self.assertEqual(out, self.game.source_text)

    def test_replacing_one_reelset_leaves_the_other_alone(self):
        new = dict(self.game.reelsets)
        new["spins_1"] = [[1] * 4 for _ in range(5)]
        out = export_text(self.game.source_text, new)
        reparsed = parse_text(out)
        self.assertEqual(reparsed.reelsets["spins_1"], [[1] * 4 for _ in range(5)])
        self.assertEqual(
            reparsed.reelsets["freespins_0"], self.game.reelsets["freespins_0"]
        )

    def test_symbols_and_paylines_survive_export(self):
        out = export_text(self.game.source_text, self.game.reelsets)
        reparsed = parse_text(out)
        self.assertEqual(reparsed.symbols, self.game.symbols)
        self.assertEqual(reparsed.paylines, self.game.paylines)

    def test_unknown_reelset_name_is_ignored(self):
        out = export_text(self.game.source_text, {"nope": [[1]]})
        self.assertEqual(out, self.game.source_text)


if __name__ == "__main__":
    unittest.main()
