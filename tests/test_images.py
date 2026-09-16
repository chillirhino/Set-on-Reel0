import tempfile
import unittest
from pathlib import Path

from reelgen.images import auto_map, id_from_name, scan_folder


class TestImages(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name)
        for name in [
            "sym1.png",
            "sym10.png",
            "sym11_1.png",
            "sym11_2.png",
            "sym2.png",
            "readme.txt",
            "background.png",
        ]:
            (self.path / name).write_bytes(b"")

    def tearDown(self):
        self.dir.cleanup()

    def test_id_from_name_takes_first_number(self):
        self.assertEqual(id_from_name("sym11_2.png"), 11)
        self.assertEqual(id_from_name("sym1.png"), 1)
        self.assertIsNone(id_from_name("background.png"))

    def test_scan_groups_variants_under_one_id(self):
        found = scan_folder(self.path)
        self.assertEqual(found[11], ["sym11_1.png", "sym11_2.png"])
        self.assertEqual(found[1], ["sym1.png"])

    def test_scan_ignores_non_images_and_nameless_files(self):
        found = scan_folder(self.path)
        self.assertNotIn(None, found)
        self.assertEqual(sorted(found), [1, 2, 10, 11])

    def test_auto_map_picks_first_variant(self):
        self.assertEqual(auto_map(self.path)[11], "sym11_1.png")

    def test_missing_folder_gives_empty_map(self):
        self.assertEqual(scan_folder(self.path / "nope"), {})


if __name__ == "__main__":
    unittest.main()
