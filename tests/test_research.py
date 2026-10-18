import unittest

from video_studio.research import parse_results, research, safe_public_url


SAMPLE_HTML = """
<div class="result">
  <a class="result__a" href="https://example.com/official">Official Source</a>
  <a class="result__snippet">Primary documentation includes exact specifications and dates.</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.org/study">Independent Study</a>
  <div class="result__snippet">A research summary with a sample size and limitations.</div>
</div>
"""


class ResearchTests(unittest.TestCase):
    def test_parses_titles_urls_and_snippets(self):
        results = parse_results(SAMPLE_HTML, "sample query", max_results=5)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Official Source")
        self.assertEqual(results[0]["url"], "https://example.com/official")
        self.assertIn("exact specifications", results[0]["snippet"])
        self.assertEqual(results[1]["url"], "https://example.org/study")

    def test_rejects_non_public_or_non_web_urls(self):
        self.assertIsNone(safe_public_url("http://127.0.0.1:8080/"))
        self.assertIsNone(safe_public_url("http://192.168.1.5/private"))
        self.assertIsNone(safe_public_url("file:///etc/passwd"))
        self.assertEqual(safe_public_url("https://example.com/page#section"), "https://example.com/page")

    def test_research_function_is_testable_without_network(self):
        def fake_search(query):
            return SAMPLE_HTML if "sample" in query else ""
        metadata, results = research("sample topic", queries=["sample topic"], max_results=2, search_fn=fake_search)
        self.assertEqual(metadata["engine"], "DuckDuckGo HTML (no API key)")
        self.assertFalse(metadata["verified"])
        self.assertEqual(metadata["result_count"], 2)
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
