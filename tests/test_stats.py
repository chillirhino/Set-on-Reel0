import unittest
from pathlib import Path

from reelgen.gameio import parse_file
from reelgen.rules import default_classes
from reelgen.stats import reel_composition, reelset_composition

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"


class TestStats(unittest.TestCase):
    def setUp(self):
        self.game = parse_file(FIXTURE)
        self.classes = default_classes(self.game)

    def test_counts_and_shares(self):
        strip = [1, 1, 1, 5, 10, 10, 10, 10]
        rows = reel_composition(strip, self.classes, self.game)
        by_id = {row["symbol_id"]: row for row in rows}
        self.assertEqual(by_id[1]["count"], 3)
        self.assertAlmostEqual(by_id[1]["share"], 3 / 8)
        self.assertEqual(by_id[10]["count"], 4)
        self.assertAlmostEqual(by_id[10]["share"], 0.5)

    def test_rows_are_sorted_by_id_and_carry_meta(self):
        rows = reel_composition([5, 1, 10], self.classes, self.game)
        self.assertEqual([row["symbol_id"] for row in rows], [1, 5, 10])
        self.assertEqual(rows[2]["kind"], "scat")
        self.assertEqual(rows[2]["asset"], "el_scatter")
        self.assertEqual(rows[0]["symbol_class"], "low")

    def test_stack_breakdown(self):
        strip = [1, 1, 5, 1, 1, 1, 5, 5]
        rows = reel_composition(strip, self.classes, self.game)
        by_id = {row["symbol_id"]: row for row in rows}
        self.assertEqual(by_id[1]["stacks"], {2: 1, 3: 1})
        self.assertEqual(by_id[5]["stacks"], {1: 1, 2: 1})

    def test_absent_symbols_are_not_listed(self):
        rows = reel_composition([1, 1, 1], self.classes, self.game)
        self.assertEqual([row["symbol_id"] for row in rows], [1])

    def test_reelset_totals_sum_across_reels(self):
        strips = [[1, 1, 5], [1, 5, 5], [10, 10, 1]]
        report = reelset_composition(strips, self.classes, self.game)
        self.assertEqual(report["lengths"], [3, 3, 3])
        self.assertEqual(len(report["reels"]), 3)
        totals = {row["symbol_id"]: row["count"] for row in report["totals"]}
        self.assertEqual(totals, {1: 4, 5: 3, 10: 2})

    def test_empty_strip(self):
        self.assertEqual(reel_composition([], self.classes, self.game), [])


if __name__ == "__main__":
    unittest.main()
