import tempfile
import unittest
from pathlib import Path

from reelgen import service

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_game.py")


class TestImport(unittest.TestCase):
    def test_import_returns_symbols_and_reelsets(self):
        out = service.import_game({"path": FIXTURE})
        self.assertEqual(len(out["symbols"]), 12)
        self.assertEqual(out["rows"], 4)
        self.assertEqual(list(out["reelsets"]), ["spins_1", "freespins_0"])
        self.assertEqual(out["default_classes"]["1"], "low")

    def test_missing_file_raises_service_error(self):
        with self.assertRaises(service.ServiceError):
            service.import_game({"path": "/nope/nope.py"})


class TestDefaultRules(unittest.TestCase):
    def test_rules_are_derived_from_current_strips(self):
        out = service.default_rules({"path": FIXTURE, "reelset": "spins_1"})
        self.assertEqual(len(out["reels"]), 5)
        first = out["reels"][0]
        total = sum(stack["count"] for stack in first["stacks"])
        self.assertEqual(total, 40)

    def test_unknown_reelset_raises(self):
        with self.assertRaises(service.ServiceError):
            service.default_rules({"path": FIXTURE, "reelset": "nope"})


class TestGenerate(unittest.TestCase):
    def test_generate_from_default_rules_round_trips(self):
        rules = service.default_rules({"path": FIXTURE, "reelset": "spins_1"})
        game = service.import_game({"path": FIXTURE})
        out = service.generate(
            {
                "path": FIXTURE,
                "reelset": "spins_1",
                "seed": 1,
                "classes": game["default_classes"],
                "reels": rules["reels"],
                "simulate": False,
            }
        )
        self.assertEqual(len(out["strips"]), 5)
        self.assertTrue(all(len(strip) == 40 for strip in out["strips"]))
        self.assertIn("math", out)
        self.assertIn("total_rtp", out["math"])
        self.assertIn("composition", out)

    def test_infeasible_rules_are_reported_before_generating(self):
        game = service.import_game({"path": FIXTURE})
        reels = [
            {
                "stacks": [
                    {"symbol_id": 1, "count": 6, "sizes": {"1": 100.0}},
                    {"symbol_id": 10, "count": 3, "sizes": {"1": 100.0}},
                    {"symbol_id": 11, "count": 3, "sizes": {"1": 100.0}},
                ],
                "distances": [
                    {
                        "a": "class:special",
                        "b": "class:special",
                        "min_gap": 5,
                        "filler": None,
                    }
                ],
            }
        ]
        out = service.generate(
            {
                "path": FIXTURE,
                "reelset": "spins_1",
                "seed": 1,
                "classes": game["default_classes"],
                "reels": reels,
                "simulate": False,
            }
        )
        self.assertTrue(out["problems"][0])
        self.assertEqual(out["strips"], [])

    def test_no_rules_raises(self):
        with self.assertRaises(service.ServiceError):
            service.generate({"path": FIXTURE, "reels": []})


class TestEvaluate(unittest.TestCase):
    def test_evaluate_existing_strips(self):
        game = service.import_game({"path": FIXTURE})
        out = service.evaluate(
            {
                "path": FIXTURE,
                "strips": game["reelsets"]["spins_1"],
                "classes": game["default_classes"],
                "simulate": False,
            }
        )
        self.assertIn("total_rtp", out["math"])
        self.assertEqual(len(out["composition"]["reels"]), 5)


class TestExport(unittest.TestCase):
    def test_export_writes_a_new_file(self):
        with tempfile.TemporaryDirectory() as folder:
            out_path = str(Path(folder) / "out.py")
            result = service.export(
                {
                    "path": FIXTURE,
                    "out_path": out_path,
                    "reelsets": {"spins_1": [[1] * 4 for _ in range(5)]},
                }
            )
            self.assertEqual(result["written"], out_path)
            text = Path(out_path).read_text(encoding="utf-8")
            self.assertIn("1 1 1 1", text)
            self.assertIn("reels_freespins_0", text)


class TestProjects(unittest.TestCase):
    def test_save_list_load(self):
        with tempfile.TemporaryDirectory() as folder:
            payload = {
                "folder": folder,
                "project": {
                    "name": "p1",
                    "game_path": FIXTURE,
                    "images_folder": "",
                    "image_map": {},
                    "rules": {"classes": {}, "reels": {}},
                    "seeds": {},
                },
            }
            service.save_project(payload)
            self.assertEqual(service.list_saved({"folder": folder})["names"], ["p1"])
            loaded = service.load_project({"folder": folder, "name": "p1"})
            self.assertEqual(loaded["project"]["name"], "p1")

    def test_load_missing_project_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(service.ServiceError):
                service.load_project({"folder": folder, "name": "nope"})


if __name__ == "__main__":
    unittest.main()
