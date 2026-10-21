import unittest

from web.markdown_renderer import render_markdown_safe


class MarkdownRendererTests(unittest.TestCase):
    def test_escapes_html_and_keeps_safe_markdown_structure(self):
        rendered = render_markdown_safe("# Title\n\n- **safe**\n\n<script>alert(1)</script>")
        self.assertIn("<h1>Title</h1>", rendered)
        self.assertIn("<ul>", rendered)
        self.assertIn("<li><strong>safe</strong></li>", rendered)
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

    def test_inline_emphasis_and_code_are_safe(self):
        rendered = render_markdown_safe("A *small* **bold** word and `<script>`")
        self.assertIn("<em>small</em>", rendered)
        self.assertIn("<strong>bold</strong>", rendered)
        self.assertIn("<code>&lt;script&gt;</code>", rendered)
        self.assertNotIn("<script>", rendered)

    def test_none_and_non_string_input_are_handled_predictably(self):
        self.assertEqual(render_markdown_safe(None), "")
        self.assertIn("<p>42</p>", render_markdown_safe(42))


if __name__ == "__main__":
    unittest.main()
