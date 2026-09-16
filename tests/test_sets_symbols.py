"""Свободные id символов и веса превращения hidden-ов.

Сеты живут в папке, поэтому каждый тест поднимает свою временную: рабочие сеты
трогать нельзя. Модуль перечитывается, так как путь к хранилищу он берёт из
окружения один раз при импорте.
"""

import importlib
import json
import os
import tempfile
import unittest


class SetsCase(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        os.environ["REELGEN_SETS"] = self._folder.name
        from reelgen import sets

        self.sets = importlib.reload(sets)
        self.sets.create_set("проба")

    def tearDown(self):
        os.environ.pop("REELGEN_SETS", None)
        self._folder.cleanup()
        from reelgen import sets

        importlib.reload(sets)  # возвращаем модулю рабочее хранилище

    def doc(self):
        return self.sets.state()

    def symbol(self, symbol_id):
        return self.sets._find(self.doc()["symbols"], symbol_id)


class TestFreeIds(SetsCase):
    def test_ids_are_no_longer_squeezed_together(self):
        """Удалили средний символ — соседи остаются на своих номерах."""
        for _ in range(3):
            self.sets.add("low")
        self.sets.delete(2)
        self.assertEqual([item["id"] for item in self.doc()["symbols"]], [1, 3])

    def test_new_symbol_takes_the_next_free_number(self):
        self.sets.add("low")
        self.sets.set_id(1, 20)
        self.assertEqual(self.sets.add("low")["id"], 21)

    def test_id_can_be_moved_far_away(self):
        self.sets.add("hidden")
        self.sets.set_id(1, 30)
        self.assertEqual([item["id"] for item in self.doc()["symbols"]], [30])

    def test_taken_id_makes_the_two_symbols_swap(self):
        """В сете, пронумерованном подряд, занято всё — иначе не переставить вообще."""
        self.sets.add("low", "туча")
        self.sets.add("middle", "гроза")
        self.sets.set_id(1, 2)
        by_id = {item["id"]: item["name"] for item in self.doc()["symbols"]}
        self.assertEqual(by_id, {1: "гроза", 2: "туча"})

    def test_id_outside_the_range_is_refused(self):
        self.sets.add("low")
        for bad in (0, -5, self.sets.MAX_ID + 1):
            with self.assertRaises(self.sets.SymbolError):
                self.sets.set_id(1, bad)
        self.assertEqual([item["id"] for item in self.doc()["symbols"]], [1])

    def test_same_id_is_a_no_op(self):
        self.sets.add("low")
        self.assertEqual(self.sets.set_id(1, 1)["id"], 1)

    def test_swap_carries_both_sides_of_every_reference(self):
        """Обмен — не «переименовали один»: ленты и стеки обоих обязаны разойтись."""
        self.sets.add("low")       # 1
        self.sets.add("middle")    # 2
        self.sets.set_reel_symbol(0, 1, {"1": 5}, False)
        self.sets.set_reel_symbol(0, 2, {"1": 3}, False)
        self.sets.generate()
        before = self.doc()["strips"][0]
        self.sets.set_id(1, 2)
        after = self.doc()["strips"][0]

        self.assertEqual(before.count(1), after.count(2))
        self.assertEqual(before.count(2), after.count(1))
        reel = self.doc()["reels"][0]
        self.assertEqual(reel["2"]["count"], 5)
        self.assertEqual(reel["1"]["count"], 3)

    def test_swapping_back_restores_everything(self):
        self.sets.add("low", "туча")
        self.sets.add("middle", "гроза")
        self.sets.set_gaps([{"a": "id:1", "b": "id:2", "min": 3, "filler": "low"}])
        before = json.dumps(self.doc()["symbols"], sort_keys=True)
        self.sets.set_id(1, 2)
        self.sets.set_id(1, 2)
        self.assertEqual(json.dumps(self.doc()["symbols"], sort_keys=True), before)
        self.assertEqual(self.doc()["gaps"][0]["a"], "id:1")


class TestIdMovesEverything(SetsCase):
    def setUp(self):
        super().setUp()
        self.sets.add("low")       # 1
        self.sets.add("middle")    # 2
        self.sets.add("special")   # 3
        self.sets.set_reel_symbol(0, 1, {"2": 3}, False)
        self.sets.set_gaps(
            [
                {"a": "id:1", "b": "id:2", "min": 4, "filler": "low"},
                {"a": "id:2", "b": "id:3", "min": 2, "filler": "low"},
            ]
        )
        self.sets.set_triggers({"symbol": 3, "min": 3}, {"symbol": 1, "min": 3})

    def test_reel_config_follows_the_new_id(self):
        self.sets.set_id(1, 20)
        reel = self.doc()["reels"][0]
        self.assertNotIn("1", reel)
        self.assertEqual(reel["20"]["stacks"], {"2": 3})
        self.assertEqual(reel["20"]["count"], 6)

    def test_gap_rules_follow_and_foreign_rules_survive(self):
        self.sets.set_id(1, 20)
        gaps = self.doc()["gaps"]
        self.assertEqual(gaps[0]["a"], "id:20")
        self.assertEqual(gaps[0]["b"], "id:2")
        self.assertEqual((gaps[1]["a"], gaps[1]["b"]), ("id:2", "id:3"))

    def test_generated_strips_follow(self):
        self.sets.generate()
        self.assertIn(1, self.doc()["strips"][0])
        self.sets.set_id(1, 20)
        strip = self.doc()["strips"][0]
        self.assertNotIn(1, strip)
        self.assertIn(20, strip)

    def test_trigger_references_follow(self):
        """Перенумерация раньше молча ломала настроенный бонус — больше нет."""
        self.sets.set_id(3, 40)
        triggers = self.doc()["triggers"]
        self.assertEqual(triggers["bonus"]["symbol"], 40)
        self.assertEqual(triggers["fs"]["symbol"], 1)

    def test_weight_references_follow(self):
        hidden = self.sets.add("hidden")["id"]
        self.sets.set_weight(hidden, 1, 10)
        self.sets.set_weight(hidden, 2, 30)
        self.sets.set_id(1, 20)
        weights = self.symbol(hidden)["weights"]
        self.assertEqual(weights, {"20": 10, "2": 30})

    def test_renaming_the_hidden_itself_keeps_its_weights(self):
        hidden = self.sets.add("hidden")["id"]
        self.sets.set_weight(hidden, 2, 7)
        self.sets.set_id(hidden, 30)
        self.assertEqual(self.symbol(30)["weights"], {"2": 7})

    def test_image_follows_the_new_id(self):
        pixel = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        self.sets.set_image(1, "sym.png", pixel)
        self.sets.set_id(1, 20)
        self.assertEqual(self.symbol(20)["image"], "sym_20.png")
        self.assertIsNotNone(self.sets.image_path(self.sets.active_set(), "sym_20.png"))
        self.assertIsNone(self.sets.image_path(self.sets.active_set(), "sym_01.png"))


class TestWeights(SetsCase):
    def setUp(self):
        super().setUp()
        self.sets.add("low")       # 1
        self.sets.add("wild")      # 2
        self.hidden = self.sets.add("hidden")["id"]   # 3

    def test_weight_is_stored_and_cleared(self):
        self.sets.set_weight(self.hidden, 1, 15)
        self.assertEqual(self.symbol(self.hidden)["weights"], {"1": 15})
        self.sets.set_weight(self.hidden, 1, 0)
        self.assertEqual(self.symbol(self.hidden)["weights"], {})

    def test_wild_is_a_legal_target(self):
        self.sets.set_weight(self.hidden, 2, 5)
        self.assertEqual(self.symbol(self.hidden)["weights"], {"2": 5})

    def test_another_hidden_is_not_a_legal_target(self):
        other = self.sets.add("hidden")["id"]
        with self.assertRaises(self.sets.SymbolError):
            self.sets.set_weight(self.hidden, other, 5)

    def test_weights_only_belong_to_hidden_symbols(self):
        with self.assertRaises(self.sets.SymbolError):
            self.sets.set_weight(1, 2, 5)

    def test_weight_must_be_a_number(self):
        with self.assertRaises(self.sets.SymbolError):
            self.sets.set_weight(self.hidden, 1, "много")

    def test_weight_on_a_deleted_symbol_is_dropped(self):
        self.sets.set_weight(self.hidden, 1, 10)
        self.sets.set_weight(self.hidden, 2, 20)
        self.sets.delete(1)
        self.assertEqual(self.symbol(self.hidden)["weights"], {"2": 20})

    def test_target_that_became_hidden_is_dropped(self):
        self.sets.set_weight(self.hidden, 1, 10)
        self.sets.update(1, kind="hidden")
        self.assertEqual(self.symbol(self.hidden)["weights"], {})

    def test_hidden_is_cut_out_of_the_pay_table(self):
        self.sets.set_pay(self.hidden, 3, 50)
        self.sets.set_pay(1, 3, 5)
        table = self.sets._pay_table(self.sets._read(self.sets.active_set()))
        self.assertIn(1, table)
        self.assertNotIn(self.hidden, table)


if __name__ == "__main__":
    unittest.main()
