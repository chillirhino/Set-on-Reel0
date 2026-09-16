import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reelgen.server import serve

FIXTURE = str(Path(__file__).parent / "fixtures" / "sample_game.py")


class TestServerSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = serve(port=0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def post(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_index_page_is_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as response:
            body = response.read().decode("utf-8")
        self.assertIn("Reel", body)
        self.assertIn("Generator", body)

    def test_app_js_is_served(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/app.js") as response:
            self.assertEqual(response.status, 200)

    def test_style_css_is_served(self):
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/style.css"
        ) as response:
            self.assertEqual(response.status, 200)

    def test_path_traversal_is_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/../reelgen/server.py"
            )
        self.assertEqual(ctx.exception.code, 404)

    def test_import_endpoint(self):
        out = self.post("/api/import", {"path": FIXTURE})
        self.assertEqual(len(out["symbols"]), 12)

    def test_full_generate_flow(self):
        game = self.post("/api/import", {"path": FIXTURE})
        rules = self.post("/api/default-rules", {"path": FIXTURE, "reelset": "spins_1"})
        out = self.post(
            "/api/generate",
            {
                "path": FIXTURE,
                "reelset": "spins_1",
                "seed": 3,
                "classes": game["default_classes"],
                "reels": rules["reels"],
                "simulate": False,
            },
        )
        self.assertEqual(len(out["strips"]), 5)
        self.assertIn("total_rtp", out["math"])

    def test_bad_path_returns_readable_error(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/import",
            data=json.dumps({"path": "/nope.py"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request)
        body = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertIn("не найден", body["error"])

    def test_unknown_route(self):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/nope",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request)
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
