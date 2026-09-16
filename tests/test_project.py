import tempfile
import unittest

from reelgen.project import Project, from_dict, list_projects, load, save, to_dict
from reelgen.rules import DistanceRule, ReelRules, RuleSet, StackRule


def sample_project():
    rules = RuleSet(
        classes={1: "low", 10: "special"},
        reels={
            "spins_1": [
                ReelRules(
                    stacks=[
                        StackRule(1, 30, {1: 60.0, 2: 40.0}),
                        StackRule(10, 4, {1: 100.0}),
                    ],
                    distances=[
                        DistanceRule("class:special", "class:special", 5, filler=None)
                    ],
                )
            ]
        },
    )
    return Project(
        name="test",
        game_path="/tmp/game.py",
        images_folder="/tmp/symbols",
        image_map={1: "sym1.png", 10: "sym10.png"},
        rules=rules,
        seeds={"spins_1": 7},
    )


class TestProjectRoundTrip(unittest.TestCase):
    def test_dict_round_trip_preserves_everything(self):
        original = sample_project()
        restored = from_dict(to_dict(original))
        self.assertEqual(restored, original)

    def test_int_keys_survive_json(self):
        restored = from_dict(to_dict(sample_project()))
        self.assertEqual(restored.image_map[1], "sym1.png")
        self.assertEqual(restored.rules.classes[10], "special")
        self.assertEqual(restored.rules.reels["spins_1"][0].stacks[0].sizes[2], 40.0)

    def test_save_and_load_from_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            path = save(sample_project(), folder)
            self.assertTrue(path.exists())
            self.assertEqual(path.name, "test.json")
            self.assertEqual(load(path), sample_project())

    def test_list_projects(self):
        with tempfile.TemporaryDirectory() as folder:
            save(sample_project(), folder)
            other = sample_project()
            other.name = "second"
            save(other, folder)
            self.assertEqual(list_projects(folder), ["second", "test"])

    def test_list_projects_on_missing_folder(self):
        self.assertEqual(list_projects("/definitely/not/here"), [])


if __name__ == "__main__":
    unittest.main()
