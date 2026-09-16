"""Модель рила: сколько стеков каждой длины. Плюс прослойка и перенос старых форм.

Главное, ради чего модель такая: **стек неделим, поэтому остатка не возникает и
одиночный символ попадает в ленту только если его заказали.** Прежняя модель
«количество символов плюс шансы на длину» подрезала последний стек по остатку и
при разрешённых длинах 2 и 3 выдавала одиночку почти в половине сборок.
"""

import importlib
import os
import random
import tempfile
import unittest

from reelgen import strips


class TestStackLengths(unittest.TestCase):
    def test_order_is_exactly_what_was_asked(self):
        self.assertEqual(
            strips.stack_lengths({"2": 6, "3": 2, "4": 2}),
            [2, 2, 2, 2, 2, 2, 3, 3, 4, 4],
        )

    def test_symbols_add_up(self):
        """6×2 + 2×3 + 2×4 = 26 — пример из постановки задачи."""
        stacks = {"2": 6, "3": 2, "4": 2}
        self.assertEqual(strips.symbols_of(stacks), 26)
        self.assertEqual(sum(strips.stack_lengths(stacks)), 26)
        self.assertEqual(len(strips.stack_lengths(stacks)), 10)

    def test_nothing_ordered_nothing_built(self):
        self.assertEqual(strips.stack_lengths({}), [])
        self.assertEqual(strips.symbols_of({}), 0)
        self.assertEqual(strips.symbols_of(None), 0)

    def test_result_never_wavers(self):
        """Случайности здесь нет вовсе: тот же заказ — тот же набор стеков."""
        stacks = {"2": 9, "3": 4}
        self.assertEqual(strips.stack_lengths(stacks), strips.stack_lengths(stacks))


class TestNoStraySingles(unittest.TestCase):
    """То, с чего началась переделка."""

    def test_forbidden_length_never_appears(self):
        cfg = {"1": {"stacks": {"2": 9, "3": 4}, "infinity": False}}
        types = {1: "low"}
        for seed in range(40):
            strip = strips.build(cfg, seed=seed, types=types)["strip"]
            runs, current = [], 1
            for index in range(1, len(strip)):
                if strip[index] == strip[index - 1]:
                    current += 1
                else:
                    runs.append(current)
                    current = 1
            runs.append(current)
            self.assertNotIn(1, runs, f"сид {seed}: одиночка в {runs}")

    def test_the_old_model_did_produce_them(self):
        """Причина зафиксирована: подрезка последнего стека по остатку."""
        rng = random.Random(3)
        singles = sum(
            1 for _ in range(400) if 1 in strips.assemble_sizes(30, {2: 70, 3: 30}, rng)
        )
        self.assertGreater(singles, 100, "старая модель обязана давать одиночки")


class TestBuild(unittest.TestCase):
    CFG = {
        "1": {"stacks": {"1": 30}, "infinity": False},
        "2": {"stacks": {"2": 10}, "infinity": False},
        "3": {"stacks": {"5": 2}, "infinity": True},
    }
    TYPES = {1: "low", 2: "middle", 3: "high"}

    def test_strip_length_is_the_sum_of_stacks(self):
        built = strips.build(self.CFG, seed=5, types=self.TYPES)
        self.assertEqual(strips.total_of(self.CFG), 30 + 20 + 10)
        self.assertEqual(len(built["strip"]), 60)

    def test_composition_is_exact(self):
        strip = strips.build(self.CFG, seed=5, types=self.TYPES)["strip"]
        self.assertEqual(strip.count(1), 30)
        self.assertEqual(strip.count(2), 20)
        self.assertEqual(strip.count(3), 10)

    def test_same_seed_gives_the_same_strip(self):
        first = strips.build(self.CFG, seed=42, types=self.TYPES)["strip"]
        second = strips.build(self.CFG, seed=42, types=self.TYPES)["strip"]
        self.assertEqual(first, second)

    def test_empty_config_builds_nothing(self):
        self.assertEqual(strips.build({}, seed=1)["strip"], [])
        self.assertEqual(strips.build({"1": {"stacks": {}}}, seed=1)["strip"], [])

    def test_infinity_only_entry_does_not_conjure_symbols(self):
        cfg = {"1": {"stacks": {}, "infinity": True}}
        self.assertEqual(strips.build(cfg, seed=1)["strip"], [])


class TestFillerLow(unittest.TestCase):
    # Два low и два не-low по десять стеков. Базовый укладчик гоняет их по кругу
    # 1-2-3-4, то есть два low встают рядом и два не-low тоже.
    CFG = {
        "1": {"stacks": {"1": 10}, "infinity": False},
        "2": {"stacks": {"1": 10}, "infinity": False},
        "3": {"stacks": {"1": 10}, "infinity": False},
        "4": {"stacks": {"1": 10}, "infinity": False},
    }
    TYPES = {1: "low", 2: "low", 3: "middle", 4: "high"}
    LOWS = {1, 2}

    def longest_run(self, strip):
        """Самая длинная полоса одного класса, лента кольцевая."""
        doubled = strip + strip
        longest, run = 0, 1
        for index in range(1, len(doubled)):
            same = (doubled[index] in self.LOWS) == (doubled[index - 1] in self.LOWS)
            run = run + 1 if same else 1
            longest = max(longest, run)
        return min(longest, len(strip))

    def test_toggle_breaks_up_long_runs_of_one_class(self):
        plain = strips.build(self.CFG, seed=11, types=self.TYPES, filler_low=False)["strip"]
        mixed = strips.build(self.CFG, seed=11, types=self.TYPES, filler_low=True)["strip"]
        self.assertLess(
            self.longest_run(mixed),
            self.longest_run(plain),
            "прослойка обязана разбивать длинные полосы дешёвого и ценного",
        )

    def test_lows_do_not_pile_up_at_the_tail(self):
        """Ровно это ломало локальное предпочтение: остаток low валился в хвост."""
        strip = strips.build(self.CFG, seed=11, types=self.TYPES, filler_low=True)["strip"]
        self.assertLessEqual(self.longest_run(strip), 5)
        self.assertEqual(sum(1 for s in strip if s in self.LOWS), 20)

    def test_toggle_does_not_touch_composition(self):
        """Прослойка меняет порядок, а не состав — значит RTP линий не двигает."""
        plain = strips.build(self.CFG, seed=11, types=self.TYPES, filler_low=False)["strip"]
        mixed = strips.build(self.CFG, seed=11, types=self.TYPES, filler_low=True)["strip"]
        self.assertEqual(sorted(plain), sorted(mixed))

    def test_toggle_survives_impossible_ratios(self):
        """low вдесятеро больше остальных — чередовать нечем, но падать нельзя."""
        cfg = {
            "1": {"stacks": {"1": 100}, "infinity": False},
            "3": {"stacks": {"1": 5}, "infinity": False},
        }
        strip = strips.build(cfg, seed=3, types=self.TYPES, filler_low=True)["strip"]
        self.assertEqual(len(strip), 105)
        self.assertEqual(strip.count(3), 5)

    def test_no_low_symbols_is_harmless(self):
        cfg = {"3": {"stacks": {"1": 10}, "infinity": False}}
        strip = strips.build(cfg, seed=3, types={3: "middle"}, filler_low=True)["strip"]
        self.assertEqual(len(strip), 10)


class TestMigration(unittest.TestCase):
    """Обе прежние формы открываются без потери состава."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        os.environ["REELGEN_SETS"] = self._folder.name
        from reelgen import sets

        self.sets = importlib.reload(sets)
        self.sets.create_set("старый")

    def tearDown(self):
        os.environ.pop("REELGEN_SETS", None)
        self._folder.cleanup()
        from reelgen import sets

        importlib.reload(sets)

    def fit(self, raw):
        return self.sets._fit_reel_symbol(raw)

    def test_oldest_shape_is_read_as_stacks(self):
        """Список пар [длина, стеков] — это уже прямо число стеков."""
        entry = self.fit({"stacks": [[2, 7], [3, 2], [4, 2]], "infinity": False})
        self.assertEqual(entry["stacks"], {"2": 7, "3": 2, "4": 2})
        self.assertEqual(entry["count"], 2 * 7 + 3 * 2 + 4 * 2)
        self.assertEqual(entry["stacks_total"], 11)

    def test_count_and_chances_keep_the_composition(self):
        """30 символов при шансах 70/30 обязаны остаться 30 символами."""
        entry = self.fit({"count": 30, "sizes": {"2": 70, "3": 30}, "infinity": False})
        self.assertEqual(entry["count"], 30)
        self.assertEqual(strips.symbols_of(entry["stacks"]), 30)
        self.assertNotIn("1", entry["stacks"], "перенос не должен заводить одиночки")

    def test_count_with_a_single_length(self):
        entry = self.fit({"count": 12, "sizes": {"1": 100}, "infinity": False})
        self.assertEqual(entry["stacks"], {"1": 12})
        self.assertEqual(entry["count"], 12)

    def test_count_without_lengths_lies_one_by_one(self):
        entry = self.fit({"count": 8, "sizes": {}, "infinity": False})
        self.assertEqual(entry["stacks"], {"1": 8})

    def test_composition_holds_across_many_shapes(self):
        """Состав — это RTP линий, поэтому расхождение проверяем по всей сетке."""
        for count in (7, 12, 25, 30, 41, 100):
            for chances in ({"2": 70, "3": 30}, {"2": 50, "3": 30, "4": 20}, {"3": 100}):
                entry = self.fit({"count": count, "sizes": chances, "infinity": False})
                drift = abs(entry["count"] - count)
                self.assertLessEqual(
                    drift, 2, f"{count} симв. при {chances} уехали на {drift}"
                )

    def test_new_shape_is_not_touched_by_migration(self):
        entry = self.fit({"stacks": {"2": 4, "5": 1}, "count": 999, "infinity": True})
        self.assertEqual(entry["stacks"], {"2": 4, "5": 1})
        self.assertEqual(entry["count"], 13)
        self.assertTrue(entry["infinity"])

    def test_migrated_set_generates_the_ordered_length(self):
        self.sets.add("low")
        self.sets.add("middle")
        name = self.sets.active_set()
        doc = self.sets._read(name)
        doc["reels"][0] = {
            "1": {"stacks": [[2, 7], [3, 2], [4, 2]], "infinity": False},
            "2": {"count": 10, "sizes": {"1": 100}, "infinity": False},
        }
        self.sets._write(name, doc)

        self.sets.generate(reel=0)
        strip = self.sets._read(name)["strips"][0]
        self.assertEqual(strip.count(1), 28)
        self.assertEqual(strip.count(2), 10)
        self.assertEqual(len(strip), 38)


if __name__ == "__main__":
    unittest.main()
