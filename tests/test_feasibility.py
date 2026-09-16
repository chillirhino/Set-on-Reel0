import unittest

from reelgen.feasibility import check_reel
from reelgen.rules import DistanceRule, ReelRules, StackRule

CLASSES = {1: "low", 2: "low", 5: "middle", 10: "special", 11: "special"}


class TestStackProblems(unittest.TestCase):
    def test_stack_size_larger_than_count(self):
        rules = ReelRules(stacks=[StackRule(10, 2, {4: 100.0})], distances=[])
        self.assertEqual([p.kind for p in check_reel(rules, CLASSES)], ["stack"])

    def test_empty_sizes(self):
        rules = ReelRules(stacks=[StackRule(10, 2, {})], distances=[])
        self.assertEqual([p.kind for p in check_reel(rules, CLASSES)], ["stack"])

    def test_zero_count_symbol_is_not_a_problem(self):
        rules = ReelRules(
            stacks=[
                StackRule(1, 10, {2: 100.0}),
                StackRule(2, 10, {2: 100.0}),
                StackRule(10, 0, {}),
            ],
            distances=[],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])


class TestSeparation(unittest.TestCase):
    def test_one_symbol_cannot_be_separated(self):
        # 10 одиночных стеков символа 1 разделять нечем: чужих стеков всего 2
        rules = ReelRules(
            stacks=[StackRule(1, 10, {1: 100.0}), StackRule(5, 2, {1: 100.0})],
            distances=[],
        )
        problems = check_reel(rules, CLASSES)
        self.assertEqual([p.kind for p in problems], ["separation"])
        self.assertIn("символ 1", problems[0].message)

    def test_bigger_stacks_make_it_separable(self):
        # те же 10 символов, но стеками по 5 — это 2 блока, их 2 чужих хватает
        rules = ReelRules(
            stacks=[StackRule(1, 10, {5: 100.0}), StackRule(5, 2, {1: 100.0})],
            distances=[],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])

    def test_balanced_composition_is_separable(self):
        rules = ReelRules(
            stacks=[
                StackRule(1, 20, {1: 100.0}),
                StackRule(2, 20, {1: 100.0}),
                StackRule(10, 4, {1: 100.0}),
            ],
            distances=[],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])


class TestDistance(unittest.TestCase):
    def test_clean_rules_have_no_problems(self):
        rules = ReelRules(
            stacks=[
                StackRule(1, 40, {2: 100.0}),
                StackRule(2, 40, {2: 100.0}),
                StackRule(10, 4, {1: 100.0}),
            ],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])

    def test_too_many_specials_for_the_distance(self):
        # 12 одиночных стеков special при дистанции 5 требуют 12 + 60 = 72 позиции
        rules = ReelRules(
            stacks=[
                StackRule(1, 20, {1: 100.0}),
                StackRule(2, 20, {1: 100.0}),
                StackRule(10, 12, {1: 100.0}),
            ],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        problems = check_reel(rules, CLASSES)
        self.assertEqual([p.kind for p in problems], ["distance"])
        self.assertIn("72", problems[0].message)
        self.assertIn("52", problems[0].message)

    def test_big_stacks_reduce_the_requirement(self):
        # те же 12 special, но стеками по 4 — это 3 блока, нужно 12 + 15 = 27
        rules = ReelRules(
            stacks=[
                StackRule(1, 20, {2: 100.0}),
                StackRule(2, 20, {2: 100.0}),
                StackRule(10, 12, {4: 100.0}),
            ],
            distances=[DistanceRule("class:special", "class:special", 5)],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])


class TestFiller(unittest.TestCase):
    def test_missing_filler_class(self):
        rules = ReelRules(
            stacks=[StackRule(5, 8, {2: 100.0}), StackRule(10, 4, {1: 100.0})],
            distances=[DistanceRule("class:special", "class:middle", 2, filler="low")],
        )
        problems = check_reel(rules, CLASSES)
        self.assertEqual([p.kind for p in problems], ["filler"])
        self.assertIn("low", problems[0].message)

    def test_filler_present_is_fine(self):
        rules = ReelRules(
            stacks=[
                StackRule(1, 20, {4: 100.0}),
                StackRule(5, 8, {2: 100.0}),
                StackRule(10, 4, {1: 100.0}),
            ],
            distances=[DistanceRule("class:special", "class:middle", 2, filler="low")],
        )
        self.assertEqual(check_reel(rules, CLASSES), [])


if __name__ == "__main__":
    unittest.main()
