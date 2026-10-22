import io
import json
import struct
import tempfile
import threading
import unittest
from http.server import HTTPServer
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
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

    def test_installable_icons_are_served_as_real_png(self):
        # A browser will not offer to install the app if the manifest's bitmap
        # icons 404 or arrive with the wrong content type.
        for path, size in (("/icon-192.png", 192), ("/icon-512.png", 512),
                           ("/icon-maskable-512.png", 512)):
            with self.subTest(path=path):
                with urlopen(self.base + path, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get("Content-Type"), "image/png")
                    body = response.read()
                self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
                self.assertEqual(struct.unpack(">II", body[16:24]), (size, size))

    def test_manifest_offers_the_sizes_an_install_prompt_requires(self):
        _, _, body = self.get("/manifest.webmanifest")
        manifest = json.loads(body)
        entries = {(icon["src"], icon.get("purpose")) for icon in manifest["icons"]}
        self.assertIn(("/icon-192.png", "any"), entries)
        self.assertIn(("/icon-512.png", "any"), entries)
        self.assertIn(("/icon-maskable-512.png", "maskable"), entries)
        self.assertFalse(manifest["prefer_related_applications"])

    def test_the_page_carries_home_screen_metadata(self):
        _, _, body = self.get("/")
        for marker in ('rel="apple-touch-icon"', 'name="mobile-web-app-capable"',
                       'content="Agent HQ"', 'rel="icon" href="/icon-192.png"'):
            with self.subTest(marker=marker):
                self.assertIn(marker, body)

    def test_the_service_worker_precaches_the_icons(self):
        _, _, body = self.get("/service-worker.js")
        for icon in ("/icon-192.png", "/icon-512.png", "/icon-maskable-512.png"):
            self.assertIn(icon, body)

    def test_arbitrary_web_asset_path_is_not_exposed(self):
        with self.assertRaises(Exception):
            self.get("/web/manifest.webmanifest")


class DashboardLaunchTests(unittest.TestCase):
    """The launcher has to behave like an app, not like a script that prints a URL."""

    def test_a_busy_port_is_explained_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            blocker = HTTPServer(("127.0.0.1", 0), dashboard.Handler)
            port = blocker.server_port
            threading.Thread(target=blocker.serve_forever, daemon=True).start()
            try:
                with self.assertRaises(SystemExit) as caught:
                    with patch.object(dashboard, "load_config", return_value={}):
                        dashboard.main(["--port", str(port), "--no-open"])
                message = str(caught.exception)
                self.assertIn("already in use", message)
                self.assertIn(str(port), message)
            finally:
                blocker.shutdown()
                blocker.server_close()

    def test_a_non_loopback_host_is_still_refused(self):
        with patch.object(dashboard, "load_config",
                          return_value={"dashboard": {"host": "0.0.0.0", "port": 8765}}):
            with self.assertRaises(SystemExit) as caught:
                dashboard.main(["--no-open"])
        self.assertIn("loopback", str(caught.exception))

    def test_an_out_of_range_port_is_refused(self):
        with patch.object(dashboard, "load_config", return_value={}):
            with self.assertRaises(SystemExit):
                dashboard.main(["--port", "70000", "--no-open"])

    def test_the_browser_is_not_opened_when_told_not_to(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(dashboard, "load_config", return_value={}), \
                 patch.object(dashboard, "BASE", Path(directory)), \
                 patch.object(dashboard, "open_when_ready") as opener, \
                 patch.object(dashboard.HTTPServer, "serve_forever", side_effect=KeyboardInterrupt):
                dashboard.main(["--port", "0", "--no-open"])
        opener.assert_not_called()

    def test_opening_the_browser_never_holds_the_process_open(self):
        with patch.object(dashboard.webbrowser, "open", return_value=True) as opened:
            timer = dashboard.open_when_ready("http://127.0.0.1:1", delay=0.01)
            timer.join(2)
        self.assertTrue(timer.daemon)
        self.assertTrue(opened.called)

    def test_a_machine_without_a_browser_still_reports_the_address(self):
        buffer = io.StringIO()
        with patch.object(dashboard.webbrowser, "open", return_value=False), \
             redirect_stdout(buffer):
            timer = dashboard.open_when_ready("http://127.0.0.1:8765", delay=0.01)
            timer.join(2)
        self.assertIn("http://127.0.0.1:8765", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
