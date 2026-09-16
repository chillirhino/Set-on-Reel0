import random
import unittest
from collections import Counter

from reelgen.generate import assemble_sizes
from reelgen.rules import StackRule


class TestAssemble(unittest.TestCase):
    def test_sum_is_always_exactly_the_count(self):
        for seed in range(50):
            rng = random.Random(seed)
            sizes = assemble_sizes(StackRule(5, 17, {1: 20.0, 2: 50.0, 3: 30.0}), rng)
            self.assertEqual(sum(sizes), 17)

    def test_single_size_only(self):
        rng = random.Random(0)
        self.assertEqual(assemble_sizes(StackRule(5, 8, {2: 100.0}), rng), [2, 2, 2, 2])

    def test_last_stack_is_trimmed_to_the_remainder(self):
        rng = random.Random(0)
        sizes = assemble_sizes(StackRule(5, 7, {3: 100.0}), rng)
        self.assertEqual(sizes, [3, 3, 1])

    def test_zero_count_gives_nothing(self):
        self.assertEqual(
            assemble_sizes(StackRule(5, 0, {1: 100.0}), random.Random(0)), []
        )

    def test_weights_are_respected_roughly(self):
        rng = random.Random(7)
        counts = Counter()
        for _ in range(400):
            counts.update(assemble_sizes(StackRule(5, 60, {1: 10.0, 4: 90.0}), rng))
        # четвёрок должно быть заметно больше единиц
        self.assertGreater(counts[4], counts[1])

    def test_same_seed_gives_same_result(self):
        a = assemble_sizes(
            StackRule(5, 20, {1: 30.0, 2: 40.0, 3: 30.0}), random.Random(3)
        )
        b = assemble_sizes(
            StackRule(5, 20, {1: 30.0, 2: 40.0, 3: 30.0}), random.Random(3)
        )
        self.assertEqual(a, b)

    def test_sizes_with_zero_weight_are_skipped(self):
        rng = random.Random(1)
        sizes = assemble_sizes(StackRule(5, 6, {1: 0.0, 3: 100.0}), rng)
        self.assertEqual(sizes, [3, 3])


if __name__ == "__main__":
    unittest.main()
