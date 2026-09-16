import unittest

from reelgen.mathexact import (
    feature_dist,
    feature_report,
    full_report,
    scatter_rtp,
    simulate_hit_rate,
    window_count_dist,
)
from reelgen.model import GameConfig, Symbol


def toy_game():
    symbols = {
        1: Symbol(1, "line", {3: 2, 4: 5, 5: 10}, "el_01"),
        9: Symbol(9, "wild", {3: 15, 4: 70, 5: 300}, "el_wild"),
        10: Symbol(10, "scat", {3: {"tb": 2, "fs": 8}}, "el_scatter"),
        11: Symbol(11, "bonus", {}, "el_bonus"),
    }
    paylines = [[0, 0, 0, 0, 0], [1, 1, 1, 1, 1], [2, 2, 2, 2, 2], [3, 3, 3, 3, 3]]
    return GameConfig(symbols=symbols, paylines=paylines, reelsets={})


class TestWindowCounts(unittest.TestCase):
    def test_distribution_sums_to_one(self):
        dist = window_count_dist([1, 1, 10, 1, 1, 1, 10, 1], 10, rows=4)
        self.assertAlmostEqual(sum(dist.values()), 1.0)

    def test_single_scatter_on_a_long_reel(self):
        # окно 4 ряда, ровно один скаттер: он виден на 4 из 8 позиций остановки
        dist = window_count_dist([10, 1, 1, 1, 1, 1, 1, 1], 10, rows=4)
        self.assertAlmostEqual(dist[1], 0.5)
        self.assertAlmostEqual(dist[0], 0.5)

    def test_no_scatter_gives_all_zero(self):
        dist = window_count_dist([1, 1, 1, 1], 10, rows=4)
        self.assertEqual(dist, {0: 1.0})

    def test_window_wraps_around_the_seam(self):
        # скаттер на последней позиции виден и когда окно перескакивает стык
        dist = window_count_dist([1, 1, 1, 1, 1, 10], 10, rows=4)
        self.assertAlmostEqual(dist[1], 4 / 6)


class TestFeatureDist(unittest.TestCase):
    def test_convolution_across_reels(self):
        # три барабана, на каждом скаттер виден с вероятностью 1/2
        strip = [10, 1, 1, 1, 1, 1, 1, 1]
        dist = feature_dist([strip, strip, strip], 10, rows=4)
        self.assertAlmostEqual(dist[3], 0.125)
        self.assertAlmostEqual(dist[0], 0.125)
        self.assertAlmostEqual(sum(dist.values()), 1.0)

    def test_report_threshold(self):
        strip = [10, 1, 1, 1, 1, 1, 1, 1]
        report = feature_report([strip, strip, strip], 10, rows=4, threshold=3)
        self.assertAlmostEqual(report["prob"], 0.125)
        self.assertAlmostEqual(report["one_in"], 8.0)

    def test_zero_probability_gives_zero_one_in(self):
        report = feature_report([[1], [1], [1]], 10, rows=4, threshold=3)
        self.assertEqual(report["prob"], 0.0)
        self.assertEqual(report["one_in"], 0.0)


class TestScatterRtp(unittest.TestCase):
    def test_pays_total_bet_multiplier(self):
        strip = [10, 1, 1, 1, 1, 1, 1, 1]
        rtp = scatter_rtp([strip, strip, strip, strip, strip], toy_game(), rows=4)
        # P(>=3 из 5 по 1/2) = 16/32 = 0.5, выплата 2 общих ставки
        self.assertAlmostEqual(rtp, 1.0)

    def test_no_scatter_symbol_gives_zero(self):
        game = GameConfig(
            symbols={1: Symbol(1, "line", {3: 2}, "el_01")}, paylines=[[0] * 5]
        )
        self.assertEqual(scatter_rtp([[1]] * 5, game, rows=4), 0.0)


class TestSimulation(unittest.TestCase):
    def test_certain_win_is_detected(self):
        strips = [[1]] * 5
        result = simulate_hit_rate(strips, toy_game(), spins=500, seed=1)
        self.assertAlmostEqual(result["prob"], 1.0)
        self.assertTrue(result["estimated"])

    def test_certain_loss_is_detected(self):
        strips = [[1], [10], [1], [1], [1]]
        result = simulate_hit_rate(strips, toy_game(), spins=500, seed=1)
        self.assertAlmostEqual(result["prob"], 0.0)

    def test_same_seed_reproduces(self):
        strip = [1, 10, 9, 11]
        a = simulate_hit_rate([strip] * 5, toy_game(), spins=2000, seed=5)
        b = simulate_hit_rate([strip] * 5, toy_game(), spins=2000, seed=5)
        self.assertEqual(a["prob"], b["prob"])


class TestFullReport(unittest.TestCase):
    def test_report_has_all_sections(self):
        strips = [[1, 10, 9, 11, 1, 1, 1, 1]] * 5
        report = full_report(strips, toy_game(), sim_spins=500, seed=1)
        for key in (
            "lines",
            "scatter",
            "bonus",
            "scatter_rtp",
            "total_rtp",
            "overall_hit",
        ):
            self.assertIn(key, report)

    def test_total_is_lines_plus_scatter(self):
        strips = [[1, 10, 9, 11, 1, 1, 1, 1]] * 5
        report = full_report(strips, toy_game(), sim_spins=500, seed=1)
        self.assertAlmostEqual(
            report["total_rtp"], report["lines"]["rtp"] + report["scatter_rtp"]
        )

    def test_simulation_can_be_skipped(self):
        strips = [[1, 10, 9, 11, 1, 1, 1, 1]] * 5
        report = full_report(strips, toy_game(), simulate=False)
        self.assertIsNone(report["overall_hit"])


if __name__ == "__main__":
    unittest.main()
