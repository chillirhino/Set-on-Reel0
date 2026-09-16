"""Мастер-рил и паттерн: пять рилов выводятся из одного эталона множителями.

Главное обещание, которое здесь проверяется: ручная настройка пяти рилов лежит
нетронутой, поэтому выключение режима возвращает её целиком. Если конфиги
начнут перезаписываться результатом, тумблер станет ловушкой.
"""

import importlib
import os
import tempfile
import unittest


class MasterCase(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        os.environ["REELGEN_SETS"] = self._folder.name
        from reelgen import sets

        self.sets = importlib.reload(sets)
        self.sets.create_set("мастер")
        for kind in ("low", "low", "middle", "special"):
            self.sets.add(kind)
        # 30, 30, 40 и 41 символов, набранные целыми стеками длин 2 и 3
        for symbol_id, stacks in (
            (1, {"2": 9, "3": 4}),
            (2, {"2": 9, "3": 4}),
            (3, {"2": 14, "3": 4}),
            (4, {"2": 10, "3": 7}),
        ):
            self.sets.set_master_symbol(symbol_id, stacks, False)

    def tearDown(self):
        os.environ.pop("REELGEN_SETS", None)
        self._folder.cleanup()
        from reelgen import sets

        importlib.reload(sets)

    def doc(self):
        return self.sets._read(self.sets.active_set())

    def counts(self, reel_index):
        reel = self.sets.effective_reels(self.doc())[reel_index]
        return {int(key): entry["count"] for key, entry in reel.items()}


class TestMultiplier(MasterCase):
    def test_off_by_default_five_reels_stay_manual(self):
        self.sets.set_reel_symbol(0, 1, {"1": 7}, False)
        self.assertEqual(self.counts(0), {1: 7})

    def test_no_pattern_means_exactly_the_master(self):
        self.sets.set_master_mode(True)
        for index in range(5):
            self.assertEqual(self.counts(index), {1: 30, 2: 30, 3: 40, 4: 41})

    def test_zero_removes_the_symbol_from_that_reel(self):
        self.sets.set_master_mode(True)
        self.sets.set_pattern("id:4", reel=2, mult=0)
        self.assertNotIn(4, self.counts(2))
        self.assertIn(4, self.counts(1))

    def test_one_changes_nothing(self):
        """Середина ползунка — ×1 при любом потолке, это и есть смысл середины."""
        self.sets.set_master_mode(True)
        for top in (2, 3, 100):
            self.sets.set_pattern("id:4", top=top)
            self.sets.set_pattern("id:4", reel=0, mult=1)
            self.assertEqual(self.counts(0)[4], 41, f"потолок ×{top}")

    def test_multiplier_scales_the_stacks_not_the_symbols(self):
        """Множитель умножает стеки: иначе снова появился бы остаток и одиночки.

        Мастер 10×2 + 7×3. При ×2.4 стеки становятся 24 и 17 (round от 24 и 16.8),
        а символы считаются уже из них: 48 + 51 = 99.
        """
        self.sets.set_master_mode(True)
        self.sets.set_pattern("id:4", top=3)
        self.sets.set_pattern("id:4", reel=4, mult=2.4)
        entry = self.sets.effective_reels(self.doc())[4]["4"]
        self.assertEqual(entry["stacks"], {"2": 24, "3": 17})
        self.assertEqual(entry["count"], 24 * 2 + 17 * 3)

    def test_multiplier_is_clamped_to_its_ceiling(self):
        self.sets.set_master_mode(True)
        self.sets.set_pattern("id:4", top=2)
        self.sets.set_pattern("id:4", reel=0, mult=9)
        self.assertEqual(self.doc()["pattern"]["id:4"]["mult"][0], 2.0)

    def test_lowering_the_ceiling_trims_existing_multipliers(self):
        self.sets.set_master_mode(True)
        self.sets.set_pattern("id:4", top=5)
        self.sets.set_pattern("id:4", reel=0, mult=4)
        self.sets.set_pattern("id:4", top=2)
        self.assertEqual(self.doc()["pattern"]["id:4"]["mult"][0], 2.0)

    def test_lengths_and_infinity_come_from_the_master_untouched(self):
        """Паттерн трогает число стеков, но не их длины и не склейку."""
        self.sets.set_master_symbol(3, {"4": 10}, True)
        self.sets.set_master_mode(True)
        self.sets.set_pattern("id:3", top=3)
        self.sets.set_pattern("id:3", reel=1, mult=2)
        entry = self.sets.effective_reels(self.doc())[1]["3"]
        self.assertEqual(entry["stacks"], {"4": 20})
        self.assertTrue(entry["infinity"])
        self.assertEqual(entry["count"], 80)

    def test_multiplier_needs_a_number(self):
        with self.assertRaises(self.sets.SymbolError):
            self.sets.set_pattern("id:4", reel=0, mult="много")

    def test_unknown_target_is_refused(self):
        for bad in ("", "type:low", "id:999", "group:нет такой"):
            with self.assertRaises(self.sets.SymbolError):
                self.sets.set_pattern(bad, reel=0, mult=1)


class TestGroupTarget(MasterCase):
    def setUp(self):
        super().setUp()
        self.sets.create_group("роялсы")
        for symbol_id in (1, 2):
            self.sets.set_group_member("роялсы", symbol_id)
        self.sets.set_master_mode(True)

    def test_group_multiplier_moves_every_member(self):
        """Половина от 9×2 + 4×3 — это 5×2 + 2×3 = 16, а не «половина от 30».

        Множитель делит стеки, а не символы, поэтому ровной половины символов
        может не получиться: 9 стеков пополам это 4.5, и половина идёт вверх.
        """
        self.sets.set_pattern("group:роялсы", reel=0, mult=0.5)
        self.assertEqual(self.counts(0)[1], 16)
        self.assertEqual(self.counts(0)[2], 16)
        self.assertEqual(self.counts(1)[1], 30)

    def test_member_has_no_target_of_its_own(self):
        """Иначе символ тянули бы две настройки и было бы неясно, какая сильнее."""
        doc = self.doc()
        self.assertEqual(self.sets.target_of(doc, 1), "group:роялсы")
        self.assertEqual(self.sets.target_of(doc, 3), "id:3")

    def test_renaming_a_group_carries_its_pattern(self):
        self.sets.set_pattern("group:роялсы", reel=0, mult=0.5)
        self.sets.rename_group("роялсы", "мелочь")
        doc = self.doc()
        self.assertNotIn("group:роялсы", doc["pattern"])
        self.assertEqual(doc["pattern"]["group:мелочь"]["mult"][0], 0.5)
        self.assertEqual(self.counts(0)[1], 16)

    def test_disbanding_a_group_drops_its_pattern(self):
        self.sets.set_pattern("group:роялсы", reel=0, mult=0.5)
        self.sets.delete_group("роялсы")
        self.assertNotIn("group:роялсы", self.doc()["pattern"])
        self.assertEqual(self.counts(0)[1], 30)


class TestModeIsReversible(MasterCase):
    def test_manual_reels_survive_generation_in_master_mode(self):
        """То, ради чего вывод идёт на ходу: пять конфигов не перезаписываются."""
        self.sets.set_reel_symbol(0, 1, {"1": 7}, False)
        self.sets.set_reel_symbol(1, 2, {"1": 9}, False)
        before = [dict(reel) for reel in self.doc()["reels"]]

        self.sets.set_master_mode(True)
        self.sets.set_pattern("id:4", reel=0, mult=0)
        self.sets.generate()

        self.assertEqual(self.doc()["reels"], before)
        self.sets.set_master_mode(False)
        self.assertEqual(self.counts(0), {1: 7})

    def test_turning_the_mode_on_seeds_the_master_from_a_reel(self):
        self.sets.clear_master()
        self.sets.set_reel_symbol(2, 3, {"2": 6}, False)
        self.sets.set_master_mode(True, from_reel=2)
        self.assertEqual(self.doc()["master"]["3"]["stacks"], {"2": 6})

    def test_seeding_does_not_overwrite_an_existing_master(self):
        self.sets.set_reel_symbol(0, 1, {"1": 99}, False)
        self.sets.set_master_mode(True, from_reel=0)
        self.assertEqual(self.doc()["master"]["1"]["count"], 30)

    def test_generated_strips_follow_the_pattern(self):
        self.sets.set_master_mode(True)
        self.sets.set_pattern("id:4", top=3)
        self.sets.set_pattern("id:4", reel=2, mult=0)
        self.sets.set_pattern("id:4", reel=4, mult=2)
        self.sets.generate()
        strips = self.doc()["strips"]
        self.assertEqual(strips[0].count(4), 41)
        self.assertEqual(strips[2].count(4), 0)
        self.assertEqual(strips[4].count(4), 82)


class TestPatternSurvivesEdits(MasterCase):
    def test_changing_an_id_carries_master_and_pattern(self):
        self.sets.set_pattern("id:4", reel=0, mult=0)
        self.sets.set_id(4, 40)
        doc = self.doc()
        self.assertIn("40", doc["master"])
        self.assertNotIn("4", doc["master"])
        self.assertEqual(doc["pattern"]["id:40"]["mult"][0], 0.0)

    def test_deleting_a_symbol_clears_its_master_and_pattern(self):
        self.sets.set_pattern("id:4", reel=0, mult=0)
        self.sets.delete(4)
        doc = self.doc()
        self.assertNotIn("4", doc["master"])
        self.assertNotIn("id:4", doc["pattern"])

    def test_old_sets_without_master_open_clean(self):
        name = self.sets.active_set()
        doc = self.sets._read(name)
        for key in ("master", "master_on", "pattern"):
            doc.pop(key, None)
        self.sets._write(name, doc)
        fresh = self.sets._read(name)
        self.assertEqual(fresh["master"], {})
        self.assertFalse(fresh["master_on"])
        self.assertEqual(fresh["pattern"], {})


if __name__ == "__main__":
    unittest.main()
