import unittest
from collections import Counter

from reelgen.generate import GenResult, generate_reel, generate_reelset
from reelgen.rules import DistanceRule, ReelRules, StackRule, violations

CLASSES = {1: "low", 2: "low", 5: "middle", 7: "high", 10: "special", 11: "special"}


def easy_rules():
    """Реалистичный состав: ни один символ не забивает ленту целиком.

    Блоков одного символа не должно быть больше, чем всех прочих вместе —
    иначе их нечем разделить и они слиплись бы в один стек.
    """
    return ReelRules(
        stacks=[
            StackRule(1, 20, {1: 60.0, 2: 40.0}),
            StackRule(2, 15, {1: 100.0}),
            StackRule(5, 12, {1: 50.0, 3: 50.0}),
            StackRule(10, 5, {1: 100.0}),
        ],
        distances=[DistanceRule("class:special", "class:special", 6)],
    )


class TestGenerateReel(unittest.TestCase):
    def test_counts_match_exactly(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        counts = Counter(result.strip)
        self.assertEqual(counts[1], 20)
        self.assertEqual(counts[2], 15)
        self.assertEqual(counts[5], 12)
        self.assertEqual(counts[10], 5)

    def test_length_is_sum_of_counts(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        self.assertEqual(len(result.strip), 52)

    def test_no_violations_on_solvable_rules(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        self.assertEqual(result.violations, [])
        self.assertIn(result.stage, ("greedy", "repair"))

    def test_stacks_never_merge_into_bigger_ones(self):
        # заказанная раскладка стеков должна выжить: слипаний быть не должно
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        self.assertEqual(result.merges, 0)
        # у символа 10 заказаны только одиночные стеки — они и должны остаться
        self.assertEqual(result.stack_actual[10], {1: 5})

    def test_result_really_satisfies_the_rules(self):
        rules = easy_rules()
        result = generate_reel(rules, CLASSES, seed=2)
        self.assertEqual(violations(result.strip, rules.distances, CLASSES), [])

    def test_same_seed_gives_the_same_strip(self):
        a = generate_reel(easy_rules(), CLASSES, seed=42)
        b = generate_reel(easy_rules(), CLASSES, seed=42)
        self.assertEqual(a.strip, b.strip)

    def test_different_seeds_give_different_strips(self):
        a = generate_reel(easy_rules(), CLASSES, seed=1)
        b = generate_reel(easy_rules(), CLASSES, seed=2)
        self.assertNotEqual(a.strip, b.strip)

    def test_stack_actual_reports_what_was_built(self):
        result = generate_reel(easy_rules(), CLASSES, seed=1)
        by_size = result.stack_actual[10]
        self.assertEqual(sum(size * n for size, n in by_size.items()), 5)

    def test_filler_rule_is_honoured(self):
        rules = ReelRules(
            stacks=[
                StackRule(1, 30, {2: 100.0}),
                StackRule(2, 10, {1: 100.0}),
                StackRule(5, 8, {1: 100.0}),
                StackRule(10, 4, {1: 100.0}),
            ],
            distances=[
                DistanceRule("class:special", "class:middle", 2, filler="low"),
                DistanceRule("class:special", "class:special", 5),
            ],
        )
        result = generate_reel(rules, CLASSES, seed=5)
        self.assertEqual(result.violations, [])
        self.assertEqual(result.merges, 0)

    def test_impossible_rules_report_failure_not_a_crash(self):
        # два разных спецсимвола не могут слипнуться, а места на дистанцию нет
        rules = ReelRules(
            stacks=[
                StackRule(1, 6, {1: 100.0}),
                StackRule(10, 3, {1: 100.0}),
                StackRule(11, 3, {1: 100.0}),
            ],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        result = generate_reel(
            rules, CLASSES, seed=1, greedy_attempts=5, repair_seconds=0.5
        )
        self.assertEqual(result.stage, "failed")
        self.assertTrue(result.violations)
        self.assertEqual(len(result.strip), 12)
        self.assertEqual(Counter(result.strip)[10], 3)

    def test_empty_rules_give_empty_strip(self):
        result = generate_reel(ReelRules(), CLASSES, seed=1)
        self.assertEqual(result.strip, [])
        self.assertEqual(result.stage, "greedy")


class TestGenerateReelset(unittest.TestCase):
    def test_five_reels_are_generated(self):
        results = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(isinstance(r, GenResult) for r in results))

    def test_reels_differ_from_each_other(self):
        results = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        strips = [tuple(r.strip) for r in results]
        self.assertEqual(len(set(strips)), 5)

    def test_reelset_is_reproducible(self):
        first = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        second = generate_reelset([easy_rules() for _ in range(5)], CLASSES, seed=9)
        self.assertEqual([r.strip for r in first], [r.strip for r in second])


if __name__ == "__main__":
    unittest.main()
