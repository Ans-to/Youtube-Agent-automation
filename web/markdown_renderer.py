"""HTML-safe Markdown rendering for the local dashboard UI."""
import html
import re


def esc(value):
    """Escape text before inserting it into generated HTML."""
    return html.escape(str(value), quote=True)


def _render_inline_safe(source):
    """Render a tiny inline Markdown subset after escaping all user-controlled text."""
    # Replace code spans first so emphasis markers inside code stay literal.
    parts = re.split(r"(`[^`]*`)", str(source))
    rendered = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            rendered.append("<code>" + esc(part[1:-1]) + "</code>")
            continue
        safe = esc(part)
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
        safe = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", safe)
        rendered.append(safe)
    return "".join(rendered)


def render_markdown_safe(source):
    """Render a safe, readable subset of Markdown without executing generated HTML."""
    output = []
    list_tag = None

    def close_list():
        nonlocal list_tag
        if list_tag:
            output.append("</" + list_tag + ">")
            list_tag = None

    for raw in str(source or "").splitlines():
        line = raw.strip()
        if not line:
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            output.append("<h" + str(level) + ">" + _render_inline_safe(heading.group(2)) + "</h" + str(level) + ">")
        elif line.startswith("- "):
            if list_tag != "ul":
                close_list()
                output.append("<ul>")
                list_tag = "ul"
            output.append("<li>" + _render_inline_safe(line[2:]) + "</li>")
        elif re.match(r"^\d+\.\s+", line):
            if list_tag != "ol":
                close_list()
                output.append("<ol>")
                list_tag = "ol"
            output.append("<li>" + _render_inline_safe(re.sub(r"^\d+\.\s+", "", line)) + "</li>")
        elif line == "---":
            close_list()
            output.append("<hr>")
        elif line.startswith("> "):
            close_list()
            output.append("<blockquote>" + _render_inline_safe(line[2:]) + "</blockquote>")
        else:
            close_list()
            output.append("<p>" + _render_inline_safe(line) + "</p>")
    close_list()
    return "\n".join(output)
