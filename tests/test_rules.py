import unittest
from pathlib import Path

from reelgen.gameio import parse_file
from reelgen.rules import (
    Block,
    DistanceRule,
    ReelRules,
    StackRule,
    blocks_of,
    default_classes,
    matches,
    penalty,
    violations,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_game.py"

# 1 = low, 5 = middle, 7 = high, 10 = special
CLASSES = {1: "low", 2: "low", 5: "middle", 7: "high", 10: "special"}


class TestBlocks(unittest.TestCase):
    def test_splits_runs(self):
        self.assertEqual(
            blocks_of([1, 1, 2, 5, 5, 5]),
            [Block(1, 0, 2), Block(2, 2, 1), Block(5, 3, 3)],
        )

    def test_merges_across_the_seam(self):
        # хвост и голова — один и тот же символ, это один блок через стык
        self.assertEqual(
            blocks_of([1, 2, 2, 1, 1]),
            [Block(2, 1, 2), Block(1, 3, 3)],
        )

    def test_uniform_strip_is_one_block(self):
        self.assertEqual(blocks_of([7, 7, 7]), [Block(7, 0, 3)])

    def test_empty_strip(self):
        self.assertEqual(blocks_of([]), [])


class TestMatches(unittest.TestCase):
    def test_class_selector(self):
        self.assertTrue(matches("class:special", 10, CLASSES))
        self.assertFalse(matches("class:special", 1, CLASSES))

    def test_id_selector(self):
        self.assertTrue(matches("id:10", 10, CLASSES))
        self.assertFalse(matches("id:10", 7, CLASSES))


class TestViolations(unittest.TestCase):
    def test_two_specials_too_close(self):
        strip = [10, 1, 1, 10, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        found = violations(strip, [rule], CLASSES)
        # одна пара нарушена (промежуток 2 < 5), вторая через стык — 6, в норме
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].gap, 2)
        self.assertEqual(found[0].deficit, 3)

    def test_specials_far_enough_pass(self):
        strip = [10, 1, 1, 1, 1, 1, 10, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_seam_gap_is_measured_through_the_wrap(self):
        # блоки на позициях 0 и 8: слева между ними 7, через стык — всего 1
        strip = [10, 1, 1, 1, 1, 1, 1, 1, 10, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        found = violations(strip, [rule], CLASSES)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].gap, 1)
        self.assertEqual(found[0].deficit, 4)

    def test_head_and_tail_of_one_symbol_are_a_single_block(self):
        # хвост и голова слиплись через стык — это один блок, нарушать нечего
        strip = [10, 1, 1, 1, 1, 1, 1, 1, 1, 10]
        rule = DistanceRule("class:special", "class:special", 5)
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_single_matching_block_never_violates(self):
        strip = [10, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 5)
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_filler_must_be_present_in_the_gap(self):
        # между special и middle два символа, но это high, а не low
        strip = [10, 7, 7, 5, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        found = violations(strip, [rule], CLASSES)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].gap, 2)
        self.assertEqual(found[0].filler_count, 0)
        self.assertEqual(found[0].deficit, 2)

    def test_filler_present_passes(self):
        strip = [10, 1, 1, 5, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_gap_longer_than_n_may_contain_anything(self):
        # промежуток 5, из них два low — требование «не меньше двух low» выполнено
        strip = [10, 7, 1, 7, 1, 7, 5, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_only_nearest_pairs_are_checked(self):
        # special .. middle . middle: между двумя middle всего один low, но пара
        # middle↔middle правилом не описана, а дальняя пара special↔второй middle
        # не проверяется, потому что между ними стоит другой middle
        strip = [10, 1, 1, 5, 1, 5, 1, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:middle", 2, filler="low")
        self.assertEqual(violations(strip, [rule], CLASSES), [])

    def test_penalty_sums_deficits(self):
        strip = [10, 1, 10, 1, 10, 1, 1, 1, 1, 1]
        rule = DistanceRule("class:special", "class:special", 4)
        self.assertEqual(penalty(strip, [rule], CLASSES), 3 + 3 + 0)


class TestDefaults(unittest.TestCase):
    def test_default_classes_from_paytable(self):
        classes = default_classes(parse_file(FIXTURE))
        self.assertEqual(classes[1], "low")
        self.assertEqual(classes[4], "low")
        self.assertEqual(classes[5], "middle")
        self.assertEqual(classes[6], "middle")
        self.assertEqual(classes[7], "high")
        self.assertEqual(classes[8], "high")
        self.assertEqual(classes[9], "special")
        self.assertEqual(classes[12], "special")


class TestReelRules(unittest.TestCase):
    def test_length_is_sum_of_counts(self):
        rules = ReelRules(
            stacks=[StackRule(1, 10, {1: 100.0}), StackRule(5, 6, {2: 100.0})],
            distances=[],
        )
        self.assertEqual(rules.length, 16)


if __name__ == "__main__":
    unittest.main()
