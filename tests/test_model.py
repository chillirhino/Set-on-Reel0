import unittest

from reelgen.model import GameConfig, Symbol


def build_game():
    symbols = {
        1: Symbol(1, "line", {3: 2, 4: 5, 5: 10}, "el_01"),
        9: Symbol(9, "wild", {3: 15, 4: 70, 5: 300}, "el_wild"),
        10: Symbol(10, "scat", {3: {"tb": 2, "fs": 8}}, "el_scatter"),
        11: Symbol(11, "bonus", {}, "el_bonus"),
    }
    paylines = [[0, 0, 0, 0, 0], [3, 2, 1, 2, 3]]
    reelsets = {"spins_1": [[1, 9, 10], [1, 1, 11], [9, 9, 1], [1, 1, 1], [10, 1, 9]]}
    return GameConfig(symbols=symbols, paylines=paylines, reelsets=reelsets)


class TestGameConfig(unittest.TestCase):
    def test_rows_is_derived_from_paylines(self):
        self.assertEqual(build_game().rows, 4)

    def test_reels_count_is_payline_length(self):
        self.assertEqual(build_game().reels_count, 5)

    def test_id_of_kind_finds_special_symbols(self):
        game = build_game()
        self.assertEqual(game.id_of_kind("wild"), 9)
        self.assertEqual(game.id_of_kind("scat"), 10)
        self.assertEqual(game.id_of_kind("bonus"), 11)
        self.assertIsNone(game.id_of_kind("hide"))

    def test_paying_symbols_excludes_scat_and_bonus(self):
        ids = [s.id for s in build_game().paying_symbols()]
        self.assertEqual(ids, [1, 9])


if __name__ == "__main__":
    unittest.main()
