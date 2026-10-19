import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "product_studio"))
import build_product


class ProductStudioTests(unittest.TestCase):
    def test_slug_is_safe_for_output_paths(self):
        self.assertEqual(build_product.slugify("../../My Product!"), "my-product")
        self.assertEqual(build_product.slugify("///"), "offline-product")

    def test_fallback_is_self_contained_and_offline_first(self):
        html = build_product.fallback_html("Demo Tool", "A private local utility")
        self.assertIn("Content-Security-Policy", html)
        self.assertIn("textarea", html)
        self.assertNotIn("<script src=", html.lower())
        self.assertNotIn("fetch(", html.lower())

    def test_static_scan_flags_network_and_dynamic_code_patterns(self):
        risky = '<script src="https://example.invalid/a.js"></script><script>fetch("/data"); eval("1")</script>'
        labels = build_product.scan_risks(risky)
        self.assertIn("external script tag", labels)
        self.assertIn("network fetch call", labels)
        self.assertIn("eval call", labels)
        self.assertIn("external URL reference", labels)

    def test_local_model_prompt_receives_supplied_research_notes(self):
        from unittest.mock import patch
        response = {
            "choices": [{
                "message": {
                    "content": "<!doctype html><html><head><title>Prototype</title></head><body>Prototype</body></html>"
                }
            }]
        }
        config = {
            "model": {
                "enabled": True,
                "base_url": "http://127.0.0.1:8080/v1/chat/completions",
                "model": "test-model",
                "max_output_tokens": 500,
                "timeout_seconds": 5,
            }
        }
        with patch.object(build_product, "post_local_model", return_value=response) as call:
            result = build_product.local_html(
                "A textile reconciliation tool",
                "Textile Reconciler",
                config,
                "Source [S1]: official documentation at https://example.com/docs",
            )
        self.assertIn("<!doctype html>", result.lower())
        prompt = call.call_args.args[1]["messages"][1]["content"]
        self.assertIn("Source [S1]", prompt)
        self.assertIn("unverified until reviewed", prompt.lower())

    def test_fallback_does_not_require_cloud_model(self):
        page = build_product.fallback_html("Simple Tool", "Test idea")
        self.assertIn("does not send the text anywhere", page)



    def test_local_model_rejects_non_loopback_and_userinfo_urls(self):
        for url in ("http://example.com:8080/v1/chat/completions",
                    "http://127.0.0.1:123@example.com:80/v1/chat/completions",
                    "https://127.0.0.1:8080/v1/chat/completions",
                    "http://127.0.0.1/v1/chat/completions"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    build_product.post_local_model(url, {}, 1)

if __name__ == "__main__":
    unittest.main()
