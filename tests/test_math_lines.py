import unittest

from reelgen.mathexact import line_report, symbol_probs
from reelgen.model import GameConfig, Symbol


def toy_game():
    symbols = {
        1: Symbol(1, "line", {3: 2, 4: 5, 5: 10}, "el_01"),
        8: Symbol(8, "line", {3: 8, 4: 40, 5: 100}, "el_08"),
        9: Symbol(9, "wild", {3: 15, 4: 70, 5: 300}, "el_wild"),
        10: Symbol(10, "scat", {3: {"tb": 2, "fs": 8}}, "el_scatter"),
    }
    return GameConfig(symbols=symbols, paylines=[[0, 0, 0, 0, 0]], reelsets={})


class TestSymbolProbs(unittest.TestCase):
    def test_probs_sum_to_one(self):
        probs = symbol_probs([1, 1, 8, 9])
        self.assertAlmostEqual(sum(probs.values()), 1.0)
        self.assertAlmostEqual(probs[1], 0.5)


class TestLineReport(unittest.TestCase):
    def test_no_wins_when_no_symbol_can_line_up(self):
        # символ 1 только на первых двух барабанах — серия максимум 2
        strips = [[1], [1], [8], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 0.0)

    def test_guaranteed_five_of_a_kind(self):
        strips = [[1], [1], [1], [1], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 10.0)
        self.assertAlmostEqual(report["per_symbol"][1], 10.0)
        self.assertAlmostEqual(report["per_length"][5], 10.0)
        self.assertAlmostEqual(report["line_hit_prob"], 1.0)

    def test_exact_three_of_a_kind(self):
        strips = [[1], [1], [1], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 2.0)
        self.assertAlmostEqual(report["per_length"][3], 2.0)

    def test_wild_completes_the_line(self):
        strips = [[1], [9], [1], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 2.0)
        self.assertAlmostEqual(report["per_symbol"][1], 2.0)

    def test_wild_run_wins_when_it_beats_the_substituted_symbol(self):
        # 9 9 9 1 1: для символа 1 серия {1,9} длиной 5 -> 10, чистый вайлд 3 -> 15
        strips = [[9], [9], [9], [1], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 15.0)
        self.assertAlmostEqual(report["per_symbol"][9], 15.0)

    def test_line_of_only_wilds_pays_the_wild_five(self):
        strips = [[9], [9], [9], [9], [9]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 300.0)
        self.assertAlmostEqual(report["per_symbol"][9], 300.0)

    def test_shorter_high_symbol_beats_longer_low_one(self):
        # 8 8 8 8 -> 40, а 1 не выстраивается вовсе; проверяем, что берётся max
        strips = [[8], [8], [8], [8], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 40.0)

    def test_max_is_taken_between_competing_symbols(self):
        # 9 9 9 8 8: для 8 серия {8,9} длиной 5 -> 100; для 9 чистая серия 3 -> 15
        strips = [[9], [9], [9], [8], [8]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 100.0)
        self.assertAlmostEqual(report["per_symbol"][8], 100.0)

    def test_scatter_never_takes_part_in_line_wins(self):
        strips = [[10], [10], [10], [10], [10]]
        report = line_report(strips, toy_game(), num_lines=1)
        self.assertAlmostEqual(report["rtp"], 0.0)

    def test_half_and_half_reel_gives_expected_average(self):
        # барабан 1: 1 или 8 поровну; остальные всегда 1
        strips = [[1, 8], [1], [1], [1], [1]]
        report = line_report(strips, toy_game(), num_lines=1)
        # 50%: 1 1 1 1 1 -> 10; 50%: 8 1 1 1 1 -> ничего (серия 8 длиной 1)
        self.assertAlmostEqual(report["rtp"], 5.0)
        self.assertAlmostEqual(report["line_hit_prob"], 0.5)
        self.assertAlmostEqual(report["line_hit_one_in"], 2.0)

    def test_num_lines_does_not_change_rtp(self):
        strips = [[1, 8], [1], [1], [1], [1]]
        one = line_report(strips, toy_game(), num_lines=1)
        twenty = line_report(strips, toy_game(), num_lines=20)
        self.assertAlmostEqual(one["rtp"], twenty["rtp"])


if __name__ == "__main__":
    unittest.main()
