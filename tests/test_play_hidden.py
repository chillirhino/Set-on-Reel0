"""Механика hidden: бросок, замена, подсчёт после замены, статистика."""

import random
import unittest

from reelgen import play

ROWS = 3
# 5 барабанов, на каждом только hidden 20 — что бы ни выпало, окно одинаковое
ALL_HIDDEN = [[20, 20, 20] for _ in range(5)]
PAYLINES = [[0, 0, 0, 0, 0], [1, 1, 1, 1, 1], [2, 2, 2, 2, 2]]
PAYS = {1: {3: 5.0, 4: 20.0, 5: 100.0}, 2: {3: 10.0, 4: 40.0, 5: 200.0}}
TYPES = {1: "low", 2: "middle", 20: "hidden"}
WEIGHTS = {20: {1: 1, 2: 1}}


class TestRoll(unittest.TestCase):
    def test_one_roll_per_hidden_id(self):
        """Три экземпляра одного hidden-а на экране дают три одинаковых символа."""
        for seed in range(30):
            result = play.one_spin(ALL_HIDDEN, ROWS, PAYLINES, PAYS, TYPES, seed, WEIGHTS)
            landed = {cell for reel in result["window"] for cell in reel}
            self.assertEqual(len(landed), 1, f"сид {seed}: на экране {landed}")
            self.assertIn(landed.pop(), (1, 2))

    def test_two_hiddens_roll_independently(self):
        """У двух hidden-ов свои распределения, и они могут дать разные цели."""
        strips = [[20, 20, 20], [20, 20, 20], [30, 30, 30], [30, 30, 30], [1, 1, 1]]
        types = {1: "low", 2: "middle", 20: "hidden", 30: "hidden"}
        weights = {20: {1: 1}, 30: {2: 1}}
        result = play.one_spin(strips, ROWS, PAYLINES, PAYS, types, 1, weights)
        self.assertEqual(result["window"][0], [1, 1, 1])
        self.assertEqual(result["window"][2], [2, 2, 2])
        self.assertEqual(result["hidden_map"], {"20": 1, "30": 2})

    def test_distribution_follows_the_weights(self):
        """На большом числе бросков доли целей сходятся к весам 1:3."""
        rng = random.Random(4242)
        tables = {20: {1: 10.0, 2: 30.0}}
        counts = {1: 0, 2: 0}
        for _ in range(20000):
            counts[play.roll_hidden(tables, rng)[20]] += 1
        share = counts[2] / (counts[1] + counts[2])
        self.assertAlmostEqual(share, 0.75, places=2)

    def test_roll_order_is_stable_for_the_same_seed(self):
        tables = {30: {1: 1.0}, 20: {2: 1.0}}
        first = play.roll_hidden(tables, random.Random(9))
        second = play.roll_hidden(tables, random.Random(9))
        self.assertEqual(first, second)


class TestSubstitutionHappensFirst(unittest.TestCase):
    def test_hidden_line_pays_as_the_target_symbol(self):
        result = play.one_spin(ALL_HIDDEN, ROWS, PAYLINES, PAYS, TYPES, 3, {20: {2: 1}})
        self.assertEqual(result["total"], 200.0 * len(PAYLINES))
        for win in result["wins"]:
            self.assertEqual(win["symbol"], 2)
            self.assertEqual(win["length"], 5)
            self.assertTrue(win["with_hidden"])

    def test_hidden_cells_are_marked_with_their_source(self):
        result = play.one_spin(ALL_HIDDEN, ROWS, PAYLINES, PAYS, TYPES, 3, {20: {2: 1}})
        self.assertEqual(result["hidden_cells"], [[20, 20, 20]] * 5)

    def test_plain_cells_are_not_marked(self):
        strips = [[20, 20, 20], [1, 1, 1], [1, 1, 1], [1, 1, 1], [1, 1, 1]]
        result = play.one_spin(strips, ROWS, PAYLINES, PAYS, TYPES, 3, {20: {1: 1}})
        self.assertEqual(result["hidden_cells"][0], [20, 20, 20])
        self.assertEqual(result["hidden_cells"][1], [0, 0, 0])

    def test_hidden_outside_the_paid_part_is_not_counted(self):
        """Hidden справа от оплаченных барабанов линию не помечает."""
        strips = [[1, 1, 1], [1, 1, 1], [1, 1, 1], [2, 2, 2], [20, 20, 20]]
        result = play.one_spin(strips, ROWS, PAYLINES, PAYS, TYPES, 3, {20: {1: 1}})
        self.assertEqual(result["wins"][0]["length"], 3)
        self.assertFalse(result["wins"][0]["with_hidden"])

    def test_hidden_turning_into_bonus_reaches_the_trigger(self):
        """Порог бонуса считается по превращённому полю."""
        strips = [[20, 20, 20], [20, 20, 20], [20, 20, 20], [1, 1, 1], [1, 1, 1]]
        types = {1: "low", 6: "special", 20: "hidden"}
        triggers = {"bonus": {"symbol": 6, "min": 3}, "fs": {}}
        report = play.simulate(
            strips, ROWS, PAYLINES, {1: {3: 5.0}}, 20.0, 50, types,
            seed=1, triggers=triggers, weights={20: {6: 1}},
        )
        self.assertEqual(report["triggers"]["bonus"]["hits"], 50)


class TestHiddenValidation(unittest.TestCase):
    def test_hidden_on_a_reel_without_weights_is_an_error(self):
        with self.assertRaises(ValueError) as caught:
            play.one_spin(ALL_HIDDEN, ROWS, PAYLINES, PAYS, TYPES, 1, {})
        self.assertIn("20", str(caught.exception))

    def test_all_zero_weights_count_as_no_weights(self):
        with self.assertRaises(ValueError):
            play.one_spin(ALL_HIDDEN, ROWS, PAYLINES, PAYS, TYPES, 1, {20: {1: 0}})

    def test_hidden_not_laid_on_any_reel_is_fine(self):
        """Символ заведён, но ни на один рил не положен — играть это не мешает."""
        strips = [[1, 1, 1] for _ in range(5)]
        result = play.one_spin(strips, ROWS, PAYLINES, PAYS, TYPES, 1, {})
        self.assertEqual(result["total"], 100.0 * len(PAYLINES))
        self.assertEqual(result["hidden_map"], {})


class TestHiddenStats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # ленты длиннее окна: hidden попадает на экран не в каждом спине
        strips = [[20, 1, 2, 1, 2, 1]] * 3 + [[1, 2, 1, 2, 1, 2]] * 2
        cls.report = play.simulate(
            strips, ROWS, PAYLINES, PAYS, 20.0, 4000, TYPES,
            seed=77, triggers={}, weights={20: {1: 30, 2: 10}},
        )

    def test_resolution_block_matches_the_weights(self):
        block = self.report["hidden"]
        self.assertEqual(len(block), 1)
        row = block[0]
        self.assertEqual(row["symbol"], 20)
        self.assertEqual(row["rolls"], 4000)
        shares = {target["symbol"]: target for target in row["targets"]}
        self.assertAlmostEqual(shares[1]["want"], 75.0, places=6)
        self.assertAlmostEqual(shares[2]["want"], 25.0, places=6)
        self.assertAlmostEqual(shares[1]["got"], 75.0, delta=2.0)
        self.assertEqual(sum(target["hits"] for target in row["targets"]), 4000)

    def test_on_screen_is_counted_separately_from_rolls(self):
        row = self.report["hidden"][0]
        self.assertLess(row["on_screen"], row["rolls"])
        self.assertGreater(row["on_screen"], 0)
        self.assertAlmostEqual(row["on_screen_rate"], row["on_screen"] / 40.0, places=6)

    def test_symbol_hits_carry_hidden_columns(self):
        for row in self.report["symbol_hits"]:
            self.assertEqual(len(row), 8)
        with_hidden = [row for row in self.report["symbol_hits"] if row[6]]
        self.assertTrue(with_hidden, "ни одна комбинация не собралась с hidden")

    def test_hidden_win_matches_the_table(self):
        self.assertAlmostEqual(
            self.report["hidden_win"],
            sum(row[7] for row in self.report["symbol_hits"]),
            places=6,
        )
        self.assertGreater(self.report["hidden_win"], 0)

    def test_hidden_never_pays_for_itself(self):
        self.assertNotIn(20, [row[0] for row in self.report["symbol_hits"]])


if __name__ == "__main__":
    unittest.main()
