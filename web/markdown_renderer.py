"""HTML-safe Markdown rendering for the local dashboard UI."""
import html
import re

def esc(value):
    """Escape text before inserting it into generated HTML."""
    return html.escape(str(value), quote=True)


def render_markdown_safe(source):
    """Render a safe, readable subset of Markdown without executing generated HTML."""
    output = []
    list_tag = None

    def close_list():
        nonlocal list_tag
        if list_tag:
            output.append("</" + list_tag + ">")
            list_tag = None

    for raw in source.splitlines():
        line = raw.strip()
        if not line:
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            output.append("<h" + str(level) + ">" + esc(heading.group(2)) + "</h" + str(level) + ">")
        elif line.startswith("- "):
            if list_tag != "ul":
                close_list()
                output.append("<ul>")
                list_tag = "ul"
            output.append("<li>" + esc(line[2:]) + "</li>")
        elif re.match(r"^\d+\.\s+", line):
            if list_tag != "ol":
                close_list()
                output.append("<ol>")
                list_tag = "ol"
            output.append("<li>" + esc(re.sub(r"^\d+\.\s+", "", line)) + "</li>")
        elif line == "---":
            close_list()
            output.append("<hr>")
        elif line.startswith("> "):
            close_list()
            output.append("<blockquote>" + esc(line[2:]) + "</blockquote>")
        else:
            close_list()
            safe = esc(line)
            safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)
            output.append("<p>" + safe + "</p>")
    close_list()
    return "\n".join(output)
