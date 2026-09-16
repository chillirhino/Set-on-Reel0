"""Эталон: сет без hidden-символов обязан играть ровно так же, как играл всегда.

Числа сняты с кода до появления hidden-ов. Если появление новой механики
сдвинуло хоть один спин или хоть одну цифру симуляции на площадке без hidden-ов
— значит сломано то, что работало. В первую очередь это ловит лишнее обращение
к генератору случайных чисел: оно сдвинуло бы всю последовательность.
"""

import unittest

from reelgen import play
from tests import fixture_play as fx


class TestSpinBaseline(unittest.TestCase):
    def spin(self, seed):
        return play.one_spin(fx.STRIPS, fx.ROWS, fx.PAYLINES, fx.PAYS, fx.TYPES, seed)

    def test_seed_5_gives_the_same_window_and_wins(self):
        result = self.spin(5)
        self.assertEqual(
            result["window"],
            [[4, 1, 2, 3], [3, 1, 4, 2], [3, 1, 2, 3], [3, 2, 1, 3], [2, 1, 3, 2]],
        )
        self.assertEqual(
            result["wins"],
            [
                {"line": 0, "symbol": 3, "length": 4, "amount": 80.0, "with_wild": True},
                {"line": 1, "symbol": 1, "length": 3, "amount": 5.0, "with_wild": False},
                {"line": 2, "symbol": 2, "length": 3, "amount": 10.0, "with_wild": True},
            ],
        )
        self.assertEqual(result["total"], 95.0)

    def test_seed_36_gives_the_same_window_and_wins(self):
        result = self.spin(36)
        self.assertEqual(
            result["window"],
            [[3, 1, 2, 3], [3, 1, 2, 3], [3, 1, 2, 3], [5, 2, 1, 3], [3, 2, 1, 3]],
        )
        self.assertEqual(
            result["wins"],
            [
                {"line": 0, "symbol": 3, "length": 3, "amount": 20.0, "with_wild": False},
                {"line": 1, "symbol": 1, "length": 3, "amount": 5.0, "with_wild": False},
                {"line": 2, "symbol": 2, "length": 3, "amount": 10.0, "with_wild": False},
                {"line": 3, "symbol": 3, "length": 5, "amount": 400.0, "with_wild": False},
            ],
        )
        self.assertEqual(result["total"], 435.0)


class TestSimulateBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = play.simulate(
            fx.STRIPS,
            fx.ROWS,
            fx.PAYLINES,
            fx.PAYS,
            fx.BET,
            20000,
            fx.TYPES,
            seed=12345,
            triggers=fx.TRIGGERS,
        )

    def test_totals_are_unchanged(self):
        self.assertEqual(self.report["rounds"], 20000)
        self.assertEqual(self.report["paying_spins"], 11716)
        self.assertEqual(self.report["total_win"], 851074.0)
        self.assertEqual(self.report["wild_win"], 490675.0)
        self.assertAlmostEqual(self.report["rtp"], 212.7685, places=4)
        self.assertAlmostEqual(self.report["hit_rate"], 58.58, places=4)
        self.assertAlmostEqual(self.report["win_avg"], 72.64202799590304, places=8)

    def test_histograms_are_unchanged(self):
        self.assertEqual(
            self.report["lines_hist"], [[1, 6007], [2, 4154], [3, 1266], [4, 271], [5, 18]]
        )
        self.assertEqual(self.report["length_hist"], [[3, 12865], [4, 4262], [5, 2160]])
        self.assertEqual(
            self.report["diversity_hist"], [[3, 206], [4, 3543], [5, 10440], [6, 5811]]
        )
        self.assertAlmostEqual(self.report["lines_avg"], 1.6462103106862411, places=8)
        self.assertAlmostEqual(self.report["length_avg"], 3.444962928397366, places=8)
        self.assertAlmostEqual(self.report["diversity_avg"], 5.0928, places=8)

    def test_win_bands_are_unchanged(self):
        self.assertEqual(
            self.report["win_values"],
            [
                [0, 1, 2908, 25549.0],
                [1, 2, 3706, 88651.0],
                [2, 3, 1148, 49725.0],
                [3, 5, 1597, 126452.0],
                [5, 10, 1031, 123880.0],
                [10, 20, 600, 131740.0],
                [20, 50, 726, 305077.0],
            ],
        )

    def test_symbol_hits_keep_their_first_six_columns(self):
        """Колонки hidden дописываются справа — эти шесть не должны сдвинуться."""
        expected = [
            [1, 3, 4370, 21850.0, 1989, 9945.0],
            [1, 4, 1514, 30280.0, 832, 16640.0],
            [1, 5, 831, 83100.0, 506, 50600.0],
            [2, 3, 4052, 40520.0, 1987, 19870.0],
            [2, 4, 1100, 44000.0, 605, 24200.0],
            [2, 5, 605, 121000.0, 388, 77600.0],
            [3, 3, 4415, 88300.0, 2047, 40940.0],
            [3, 4, 1648, 131840.0, 906, 72480.0],
            [3, 5, 724, 289600.0, 446, 178400.0],
            [4, 3, 11, 550.0, 0, 0.0],
            [4, 4, 0, 0.0, 0, 0.0],
            [4, 5, 0, 0.0, 0, 0.0],
            [5, 3, 17, 34.0, 0, 0.0],
        ]
        rows = self.report["symbol_hits"]
        self.assertEqual(len(rows), len(expected))
        for row, want in zip(rows, expected):
            self.assertEqual(row[:6], want)

    def test_hits_add_up_to_the_totals(self):
        """Блок «RTP по длине» складывает symbol_hits — суммы обязаны биться.

        Разъедься здесь счёт или деньги, и блок начал бы врать тихо: цифры
        выглядели бы правдоподобно, но не сходились бы с общим RTP.
        """
        by_length: dict[int, list] = {}
        for _, length, count, amount, *_ in self.report["symbol_hits"]:
            slot = by_length.setdefault(length, [0, 0.0])
            slot[0] += count
            slot[1] += amount

        counts = {length: slot[0] for length, slot in by_length.items() if slot[0]}
        self.assertEqual(counts, dict(self.report["length_hist"]))
        self.assertAlmostEqual(
            sum(slot[1] for slot in by_length.values()), self.report["total_win"], places=6
        )

        staked = self.report["bet"] * self.report["rounds"]
        points = sum(slot[1] / staked * 100 for slot in by_length.values())
        self.assertAlmostEqual(points, self.report["rtp"], places=9)

    def test_triggers_are_unchanged(self):
        bonus = self.report["triggers"]["bonus"]
        self.assertEqual((bonus["symbol"], bonus["min"], bonus["hits"]), (6, 3, 1141))
        self.assertEqual(bonus["ant"]["hits"], 2029)
        fs = self.report["triggers"]["fs"]
        self.assertEqual((fs["symbol"], fs["min"], fs["hits"]), (5, 3, 1142))
        self.assertEqual(fs["ant"]["hits"], 719)



class TestScreenStats(unittest.TestCase):
    """Роялсы, вайлды и рилы с вайлдом — считаются по экрану после стопа."""

    @classmethod
    def setUpClass(cls):
        cls.report = play.simulate(
            fx.STRIPS, fx.ROWS, fx.PAYLINES, fx.PAYS, fx.BET, 20000, fx.TYPES,
            seed=12345, triggers=fx.TRIGGERS,
        )

    def test_screen_size_is_rows_by_reels(self):
        self.assertEqual(self.report["screen"], fx.ROWS * len(fx.STRIPS))

    def test_every_spin_lands_in_each_histogram(self):
        for key in ("royal_hist", "wild_hist", "wild_reels_hist"):
            total = sum(count for _, count in self.report[key])
            self.assertEqual(total, self.report["rounds"], key)

    def test_royals_and_pictures_fill_the_screen(self):
        """Они дополняют друг друга: одно распределение описывает оба."""
        self.assertAlmostEqual(
            self.report["royal_avg"] + self.report["picture_avg"],
            self.report["screen"],
            places=9,
        )

    def test_counts_stay_inside_the_screen(self):
        for count, _ in self.report["royal_hist"]:
            self.assertTrue(0 <= count <= self.report["screen"], count)
        for count, _ in self.report["wild_hist"]:
            self.assertTrue(0 <= count <= self.report["screen"], count)

    def test_wild_reels_never_exceed_the_reel_count(self):
        for count, _ in self.report["wild_reels_hist"]:
            self.assertTrue(0 <= count <= len(fx.STRIPS), count)

    def test_dry_spins_agree_across_both_wild_histograms(self):
        """Ноль вайлдов и ноль рилов с вайлдом — это один и тот же спин."""
        by_count = dict(self.report["wild_hist"])
        by_reels = dict(self.report["wild_reels_hist"])
        self.assertEqual(by_count.get(0, 0), by_reels.get(0, 0))

    def test_reels_with_wilds_never_exceed_wilds(self):
        """На риле с вайлдом их минимум один, поэтому среднее по рилам не больше."""
        self.assertLessEqual(self.report["wild_reels_avg"], self.report["wild_avg"])

    def test_royals_match_the_strip_composition(self):
        """Доля роялсов на экране обязана совпасть с их долей в лентах."""
        lows = {sid for sid, kind in fx.TYPES.items() if kind == "low"}
        on_strips = sum(1 for strip in fx.STRIPS for sid in strip if sid in lows)
        total = sum(len(strip) for strip in fx.STRIPS)
        self.assertAlmostEqual(
            self.report["royal_avg"] / self.report["screen"],
            on_strips / total,
            delta=0.02,
        )


class TestHiddenCountsAfterSubstitution(unittest.TestCase):
    def test_a_hidden_turned_wild_counts_as_a_wild(self):
        """На стопе скрытого уже нет — в статистику идёт то, чем он стал."""
        strips_ = [[20, 20, 20, 20]] * 5
        types = {7: "wild", 20: "hidden"}
        report = play.simulate(
            strips_, 4, fx.PAYLINES, {7: {3: 1.0}}, 20.0, 50, types,
            seed=1, triggers={}, weights={20: {7: 100}},
        )
        self.assertEqual(report["wild_hist"], [[20, 50]])
        self.assertEqual(report["wild_reels_hist"], [[5, 50]])
        self.assertEqual(report["royal_avg"], 0.0)

    def test_a_hidden_turned_royal_counts_as_a_royal(self):
        strips_ = [[20, 20, 20, 20]] * 5
        types = {1: "low", 20: "hidden"}
        report = play.simulate(
            strips_, 4, fx.PAYLINES, {1: {3: 1.0}}, 20.0, 50, types,
            seed=1, triggers={}, weights={20: {1: 100}},
        )
        self.assertEqual(report["royal_avg"], 20.0)
        self.assertEqual(report["picture_avg"], 0.0)
        self.assertEqual(report["wild_avg"], 0.0)


if __name__ == "__main__":
    unittest.main()
