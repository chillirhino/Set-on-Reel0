"""Сквозной путь скрытого символа: завести, увезти на id 20, дать веса, сыграть.

Проверка идёт через настоящий HTTP: маршруты, разбор payload и текст ошибок —
ровно то, что увидит интерфейс.
"""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


class TestHiddenOverHttp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._folder = tempfile.TemporaryDirectory()
        os.environ["REELGEN_SETS"] = cls._folder.name
        import importlib

        from reelgen import sets

        importlib.reload(sets)
        from reelgen import server

        importlib.reload(server)

        cls.httpd = server.serve(port=0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.environ.pop("REELGEN_SETS", None)
        cls._folder.cleanup()
        import importlib

        from reelgen import sets, server

        importlib.reload(sets)
        importlib.reload(server)

    def post(self, path, payload=None):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def error(self, path, payload):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post(path, payload)
        return json.loads(caught.exception.read().decode("utf-8"))["error"]

    def test_hidden_from_setup_to_simulation(self):
        self.post("/api/sets/create", {"name": "скрытые"})
        for kind in ("low", "middle", "wild"):
            self.post("/api/symbols/add", {"type": kind})
        state = self.post("/api/symbols/add", {"type": "hidden"})
        self.assertEqual([item["type"] for item in state["symbols"]][-1], "hidden")

        # скрытый уезжает на 20 — ради этого и делались свободные номера
        state = self.post("/api/symbols/id", {"id": 4, "new_id": 20})
        self.assertEqual([item["id"] for item in state["symbols"]], [1, 2, 3, 20])

        # занятый номер — обмен: иначе в сете, пронумерованном подряд, не переставить
        state = self.post("/api/symbols/id", {"id": 1, "new_id": 2})
        self.assertEqual([item["type"] for item in state["symbols"]][:2], ["middle", "low"])
        self.post("/api/symbols/id", {"id": 1, "new_id": 2})  # вернули как было

        self.assertIn(
            "hidden", self.error("/api/symbols/weight", {"id": 20, "target": 20, "weight": 5})
        )

        for length, amount in ((3, 5), (4, 20), (5, 100)):
            self.post("/api/symbols/pay", {"id": 1, "length": length, "amount": amount})
            self.post("/api/symbols/pay", {"id": 2, "length": length, "amount": amount * 2})
        self.post("/api/symbols/weight", {"id": 20, "target": 1, "weight": 30})
        state = self.post("/api/symbols/weight", {"id": 20, "target": 2, "weight": 10})
        hidden = [item for item in state["symbols"] if item["type"] == "hidden"][0]
        self.assertEqual(hidden["weights"], {"1": 30, "2": 10})

        for reel in range(5):
            for symbol_id, count in ((1, 8), (2, 8), (3, 2), (20, 4)):
                self.post(
                    "/api/reels/symbol",
                    {"reel": reel, "symbol": symbol_id, "stacks": {"1": count},
                     "infinity": False},
                )
        state = self.post("/api/reels/generate", {})
        self.assertIn(20, state["strips"][0])

        spin = self.post("/api/play/spin", {"seed": 3})
        landed = {
            spin["window"][reel][row]
            for reel, column in enumerate(spin["hidden_cells"])
            for row, source in enumerate(column)
            if source == 20
        }
        self.assertTrue(landed, "скрытый ни разу не попал на экран при сиде 3")
        self.assertEqual(len(landed), 1, "все копии скрытого обязаны стать одним символом")
        self.assertEqual(spin["hidden_map"], {"20": landed.pop()})
        self.assertNotIn(20, [cell for reel in spin["window"] for cell in reel])

        report = self.post("/api/play/simulate", {"rounds": 5000})
        block = report["hidden"][0]
        self.assertEqual(block["symbol"], 20)
        self.assertEqual(block["rolls"], 5000)
        shares = {target["symbol"]: target["got"] for target in block["targets"]}
        self.assertAlmostEqual(shares[1], 75.0, delta=2.5)
        self.assertGreater(report["hidden_win"], 0)
        self.assertTrue(all(len(row) == 8 for row in report["symbol_hits"]))

    def test_playing_without_weights_explains_itself(self):
        self.post("/api/sets/create", {"name": "без весов"})
        self.post("/api/symbols/add", {"type": "low"})
        self.post("/api/symbols/add", {"type": "hidden"})
        self.post("/api/symbols/pay", {"id": 1, "length": 3, "amount": 5})
        for reel in range(5):
            for symbol_id in (1, 2):
                self.post(
                    "/api/reels/symbol",
                    {"reel": reel, "symbol": symbol_id, "stacks": {"1": 5},
                     "infinity": False},
                )
        self.post("/api/reels/generate", {})

        message = self.error("/api/play/simulate", {"rounds": 100})
        self.assertIn("веса превращения", message)
        self.assertIn("2", message)


if __name__ == "__main__":
    unittest.main()
