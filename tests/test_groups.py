"""Группы символов: членство общее на сет, значения — во все члены сразу.

Группа не хранит значения, она их рассылает. Поэтому главное, что здесь надо
проверить: рассылка доходит до всех, членство переживает правки символов, и
разбор группы ничего не теряет.
"""

import importlib
import os
import tempfile
import unittest


class GroupCase(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        os.environ["REELGEN_SETS"] = self._folder.name
        from reelgen import sets

        self.sets = importlib.reload(sets)
        self.sets.create_set("группы")
        for kind in ("low", "low", "low", "low", "middle", "special"):
            self.sets.add(kind)

    def tearDown(self):
        os.environ.pop("REELGEN_SETS", None)
        self._folder.cleanup()
        from reelgen import sets

        importlib.reload(sets)

    def doc(self):
        return self.sets.state()

    def royals(self):
        self.sets.create_group("роялсы")
        for symbol_id in (1, 2, 3, 4):
            self.sets.set_group_member("роялсы", symbol_id)
        return self.doc()["groups"][0]


class TestMembership(GroupCase):
    def test_group_starts_empty(self):
        self.sets.create_group("роялсы")
        self.assertEqual(self.doc()["groups"], [{"name": "роялсы", "members": []}])

    def test_members_join_and_leave(self):
        self.royals()
        self.assertEqual(self.doc()["groups"][0]["members"], [1, 2, 3, 4])
        self.sets.set_group_member("роялсы", 3, join=False)
        self.assertEqual(self.doc()["groups"][0]["members"], [1, 2, 4])

    def test_symbol_belongs_to_one_group_only(self):
        """Иначе «применить ко всем» перестаёт иметь однозначный смысл."""
        self.royals()
        self.sets.create_group("картинки")
        self.sets.set_group_member("картинки", 1)
        groups = {item["name"]: item["members"] for item in self.doc()["groups"]}
        self.assertEqual(groups["роялсы"], [2, 3, 4])
        self.assertEqual(groups["картинки"], [1])

    def test_duplicate_name_is_refused(self):
        self.sets.create_group("роялсы")
        with self.assertRaises(self.sets.SymbolError):
            self.sets.create_group("роялсы")

    def test_rename_keeps_members(self):
        self.royals()
        self.sets.rename_group("роялсы", "мелочь")
        groups = self.doc()["groups"]
        self.assertEqual(groups[0]["name"], "мелочь")
        self.assertEqual(groups[0]["members"], [1, 2, 3, 4])

    def test_rename_onto_a_taken_name_is_refused(self):
        self.sets.create_group("роялсы")
        self.sets.create_group("картинки")
        with self.assertRaises(self.sets.SymbolError):
            self.sets.rename_group("роялсы", "картинки")

    def test_missing_group_is_an_error(self):
        with self.assertRaises(self.sets.SymbolError):
            self.sets.set_group_member("нет такой", 1)


class TestBroadcast(GroupCase):
    def test_one_value_reaches_every_member(self):
        self.royals()
        self.sets.set_reel_group(0, "роялсы", {"2": 9, "3": 4}, False)
        reel = self.doc()["reels"][0]
        for symbol_id in ("1", "2", "3", "4"):
            self.assertEqual(
                reel[symbol_id],
                {"stacks": {"2": 9, "3": 4}, "infinity": False, "count": 30, "stacks_total": 13},
            )

    def test_value_is_copied_not_split(self):
        """30 на группу из четырёх — это 120 символов в ленте, а не 30."""
        self.royals()
        self.sets.set_reel_group(0, "роялсы", {"1": 30}, False)
        self.sets.generate(reel=0)
        strip = self.doc()["strips"][0]
        self.assertEqual(len(strip), 120)
        for symbol_id in (1, 2, 3, 4):
            self.assertEqual(strip.count(symbol_id), 30)

    def test_infinity_travels_with_the_group(self):
        """Поля членов заморожены, поэтому ∞ обязана рассылаться тоже."""
        self.royals()
        self.sets.set_reel_group(0, "роялсы", {"2": 5}, True)
        reel = self.doc()["reels"][0]
        self.assertTrue(all(reel[str(i)]["infinity"] for i in (1, 2, 3, 4)))

    def test_zero_count_removes_members_from_the_reel(self):
        self.royals()
        self.sets.set_reel_group(0, "роялсы", {"1": 10}, False)
        self.sets.set_reel_group(0, "роялсы", {}, False)
        self.assertEqual(self.doc()["reels"][0], {})

    def test_values_are_per_reel(self):
        """Членство общее на сет, а числа у каждого рила свои."""
        self.royals()
        self.sets.set_reel_group(0, "роялсы", {"1": 30}, False)
        self.sets.set_reel_group(1, "роялсы", {"1": 5}, False)
        reels = self.doc()["reels"]
        self.assertEqual(reels[0]["1"]["count"], 30)
        self.assertEqual(reels[1]["1"]["count"], 5)

    def test_empty_group_cannot_be_configured(self):
        self.sets.create_group("пустая")
        with self.assertRaises(self.sets.SymbolError):
            self.sets.set_reel_group(0, "пустая", {"1": 10}, False)


class TestGroupSurvivesEdits(GroupCase):
    def test_deleting_a_group_keeps_the_values(self):
        self.royals()
        self.sets.set_reel_group(0, "роялсы", {"2": 6}, False)
        self.sets.delete_group("роялсы")
        self.assertEqual(self.doc()["groups"], [])
        reel = self.doc()["reels"][0]
        self.assertEqual(reel["1"]["stacks"], {"2": 6})
        self.assertEqual(reel["1"]["count"], 12)

    def test_deleting_a_symbol_drops_it_from_its_group(self):
        self.royals()
        self.sets.delete(2)
        self.assertEqual(self.doc()["groups"][0]["members"], [1, 3, 4])

    def test_changing_an_id_carries_membership(self):
        self.royals()
        self.sets.set_id(4, 40)
        self.assertEqual(self.doc()["groups"][0]["members"], [1, 2, 3, 40])

    def test_swapping_ids_keeps_both_sides_consistent(self):
        """Обмен 4 и 5: в группе должен оказаться ровно один из них."""
        self.royals()
        self.sets.set_id(4, 5)
        members = self.doc()["groups"][0]["members"]
        self.assertEqual(members, [1, 2, 3, 5])

    def test_group_survives_save_and_reload(self):
        self.royals()
        self.sets.save_set()
        self.assertEqual(self.doc()["groups"][0]["members"], [1, 2, 3, 4])

    def test_dead_ids_are_dropped_on_read(self):
        name = self.sets.active_set()
        doc = self.sets._read(name)
        doc["groups"] = [{"name": "мусор", "members": [1, 999]}]
        self.sets._write(name, doc)
        self.assertEqual(self.sets._read(name)["groups"][0]["members"], [1])

    def test_old_sets_without_groups_open_clean(self):
        name = self.sets.active_set()
        doc = self.sets._read(name)
        doc.pop("groups", None)
        self.sets._write(name, doc)
        self.assertEqual(self.sets._read(name)["groups"], [])


if __name__ == "__main__":
    unittest.main()
