import unittest
from pathlib import Path

from reelgen.gameio import ParseError, parse_file, parse_text

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"


class TestParse(unittest.TestCase):
    def setUp(self):
        self.game = parse_file(FIXTURE)

    def test_parses_all_twelve_symbols(self):
        self.assertEqual(sorted(self.game.symbols), list(range(1, 13)))

    def test_symbol_fields(self):
        s5 = self.game.symbols[5]
        self.assertEqual(s5.kind, "line")
        self.assertEqual(s5.pays, {3: 5, 4: 25, 5: 50})
        self.assertEqual(s5.asset, "el_05")

    def test_scatter_pays_keep_nested_dict(self):
        self.assertEqual(self.game.symbols[10].pays, {3: {"tb": 2, "fs": 8}})

    def test_empty_pays_stay_empty(self):
        self.assertEqual(self.game.symbols[11].pays, {})

    def test_parses_twenty_paylines_in_order(self):
        self.assertEqual(len(self.game.paylines), 20)
        self.assertEqual(self.game.paylines[0], [0, 0, 0, 0, 0])
        self.assertEqual(self.game.paylines[19], [3, 2, 2, 2, 3])

    def test_parses_reelsets_in_file_order(self):
        self.assertEqual(list(self.game.reelsets), ["spins_1", "freespins_0"])

    def test_reelset_shape_and_content(self):
        reels = self.game.reelsets["spins_1"]
        self.assertEqual(len(reels), 5)
        self.assertTrue(all(len(r) == 40 for r in reels))
        self.assertEqual(reels[0][:5], [5, 5, 5, 5, 1])

    def test_source_text_is_kept_for_export(self):
        self.assertIn("reels_spins_1", self.game.source_text)

    def test_bad_symbol_line_raises(self):
        with self.assertRaises(ParseError):
            parse_text("symbol_01 = 'line', {3: 2}\n")


if __name__ == "__main__":
    unittest.main()
