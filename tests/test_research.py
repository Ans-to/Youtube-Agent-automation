import unittest

from video_studio.research import PageTextParser, fetch_page, parse_results, research, safe_public_url, sanitize_research_query


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

    def test_extracts_page_text_and_ignores_scripts(self):
        parser = PageTextParser()
        parser.feed("<html><title>Example title</title><body><main><h1>Useful heading</h1><p>Readable evidence.</p><script>secret()</script></main></body></html>")
        title, text = parser.result()
        self.assertEqual(title, "Example title")
        self.assertIn("Useful heading", text)
        self.assertIn("Readable evidence", text)
        self.assertNotIn("secret()", text)

    def test_research_query_redacts_common_identifiers_and_secrets(self):
        query = sanitize_research_query(
            "Find docs for API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456 and user@example.com phone 03001234567"
        )
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", query)
        self.assertNotIn("user@example.com", query)
        self.assertIn("[REDACTED_SECRET]", query)
        self.assertIn("[REDACTED_EMAIL]", query)
        self.assertIn("[REDACTED_PHONE]", query)

    def test_page_fetch_rejects_private_address_without_request(self):
        result = fetch_page("http://127.0.0.1/private")
        self.assertEqual(result["fetch_status"], "rejected")

    def test_page_fetch_selection_covers_multiple_queries(self):
        fetched = []
        def fake_search(query):
            if "official" in query:
                label = "official"
            elif "risks" in query:
                label = "risks"
            else:
                label = "primary"
            return (
                '<a class="result__a" href="https://example.com/' + label + '">' + label + '</a>'
                '<div class="result__snippet">Evidence for ' + label + '</div>'
            )
        def fake_page(url):
            fetched.append(url)
            return {"fetch_status": "fetched", "page_title": "Title", "page_text": "Page evidence"}
        metadata, results = research(
            "topic",
            queries=["topic", "topic official", "topic risks"],
            max_results=3,
            search_fn=fake_search,
            page_fetch_fn=fake_page,
        )
        self.assertEqual(metadata["pages_fetched"], 3)
        self.assertEqual(len(fetched), 3)
        self.assertIn("https://example.com/official", fetched)
        self.assertIn("https://example.com/risks", fetched)
        self.assertEqual(len(results), 3)

    def test_research_function_is_testable_without_network(self):
        def fake_search(query):
            return SAMPLE_HTML if "sample" in query else ""
        def fake_page(url):
            return {"fetch_status": "fetched", "page_title": "Sample page", "page_text": "Evidence text from a test fixture."}
        metadata, results = research("sample topic", queries=["sample topic"], max_results=2,
                                     search_fn=fake_search, page_fetch_fn=fake_page)
        self.assertEqual(metadata["engine"], "DuckDuckGo HTML (no API key)")
        self.assertFalse(metadata["verified"])
        self.assertEqual(metadata["source_provenance_schema"], 1)
        self.assertEqual(metadata["pages_fetched"], 2)
        self.assertEqual(results[0]["page_text"], "Evidence text from a test fixture.")
        self.assertEqual(results[0]["source_id"], "S1")
        self.assertEqual(results[0]["requested_domain"], "example.com")
        self.assertEqual(results[0]["final_domain"], "example.com")
        self.assertEqual(len(results[0]["page_text_sha256"]), 64)
        self.assertEqual(metadata["result_count"], 2)
        self.assertEqual(len(results), 2)


if __name__ == "__main__":
    unittest.main()
