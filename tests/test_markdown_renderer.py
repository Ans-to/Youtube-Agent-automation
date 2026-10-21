import unittest

from web.markdown_renderer import render_markdown_safe


class MarkdownRendererTests(unittest.TestCase):
    def test_escapes_html_and_keeps_safe_markdown_structure(self):
        rendered = render_markdown_safe("# Title\n\n- **safe**\n\n<script>alert(1)</script>")
        self.assertIn("<h1>Title</h1>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertNotIn("<script>", rendered)

    def test_closes_lists_when_switching_list_types(self):
        rendered = render_markdown_safe("- one\n- two\n1. three")
        self.assertIn("</ul>\n<ol>", rendered)
        self.assertTrue(rendered.endswith("</ol>"))

    def test_escapes_quotes_and_does_not_execute_markdown_html(self):
        rendered = render_markdown_safe('<img src=x onerror="alert(1)">')
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;img", rendered)


if __name__ == "__main__":
    unittest.main()
