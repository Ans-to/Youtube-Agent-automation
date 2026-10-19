import json
import threading
import unittest
from http.server import HTTPServer
from urllib.request import urlopen

import dashboard


class DashboardPwaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), dashboard.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, path):
        with urlopen(self.base + path, timeout=3) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8")

    def test_dashboard_links_to_installable_manifest(self):
        status, content_type, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('rel="manifest" href="/manifest.webmanifest"', body)
        self.assertIn("serviceWorker.register('/service-worker.js')", body)

    def test_manifest_has_mobile_install_metadata(self):
        status, content_type, body = self.get("/manifest.webmanifest")
        self.assertEqual(status, 200)
        self.assertIn("application/manifest+json", content_type)
        manifest = json.loads(body)
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        self.assertTrue(manifest["icons"])

    def test_only_fixed_pwa_assets_are_served(self):
        for path, marker in (
            ("/service-worker.js", "Never cache task state"),
            ("/icon.svg", "<svg"),
            ("/offline.html", "local Python dashboard"),
        ):
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertIn(marker, body)

    def test_arbitrary_web_asset_path_is_not_exposed(self):
        with self.assertRaises(Exception):
            self.get("/web/manifest.webmanifest")


if __name__ == "__main__":
    unittest.main()
