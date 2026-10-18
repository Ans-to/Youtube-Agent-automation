#!/usr/bin/env python3
"""Collect free web-search leads without API keys; sources are not automatically verified."""
import argparse
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


SEARCH_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "OfflineAgentHQ-Research/1.0 (+local-first research utility)"
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = (ROOT / "workspace").resolve()


def safe_public_url(value):
    try:
        parts = urllib.parse.urlsplit(value)
        if parts.scheme not in {"https", "http"} or not parts.hostname or parts.username or parts.password:
            return None
        host = parts.hostname.lower().rstrip(".")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            return None
        try:
            ip = ipaddress.ip_address(host)
            if not ip.is_global:
                return None
        except ValueError:
            pass
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    except (ValueError, UnicodeError):
        return None


def unwrap_result_url(value):
    value = urllib.parse.urljoin(SEARCH_URL, value)
    parts = urllib.parse.urlsplit(value)
    if parts.hostname and (parts.hostname == "duckduckgo.com" or parts.hostname.endswith(".duckduckgo.com")) and parts.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parts.query).get("uddg", [""])[0]
        value = urllib.parse.unquote(target)
    return safe_public_url(value)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Search redirects are disabled", headers, fp)


class ResultParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.active = None
        self.mode = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self.active = {"title": "", "url": unwrap_result_url(attrs.get("href", "")), "snippet": ""}
            self.results.append(self.active)
            self.mode = "title"
        elif self.results and ("result__snippet" in classes or "result__snippet" in (attrs.get("class") or "")):
            self.active = self.results[-1]
            self.mode = "snippet"

    def handle_data(self, data):
        if self.active is not None and self.mode in {"title", "snippet"}:
            self.active[self.mode] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.mode == "title":
            self.active = None
            self.mode = None
        elif tag == "a" and self.mode == "snippet":
            self.active = None
            self.mode = None
        elif tag in {"div", "span"} and self.mode == "snippet":
            self.active = None
            self.mode = None


def fetch_search_html(query, timeout=15):
    request = urllib.request.Request(
        SEARCH_URL + "?" + urllib.parse.urlencode({"q": query}),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Encoding": "identity"},
        method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=max(3, min(int(timeout), 30))) as response:
        if response.status != 200:
            raise ValueError("Search engine returned HTTP " + str(response.status))
        data = response.read(1_500_001)
    if len(data) > 1_500_000:
        raise ValueError("Search response exceeded the 1.5 MB limit.")
    return data.decode("utf-8", errors="replace")


def parse_results(markup, query, max_results=6):
    parser = ResultParser()
    parser.feed(markup)
    results = []
    seen = set()
    for item in parser.results:
        url = item.get("url")
        title = " ".join(item.get("title", "").split())
        snippet = " ".join(item.get("snippet", "").split())
        if not url or not title or url in seen:
            continue
        seen.add(url)
        results.append({"query": query, "title": title[:300], "url": url, "snippet": snippet[:1000]})
        if len(results) >= max(1, min(int(max_results), 15)):
            break
    return results


def research(topic, queries=None, max_results=5, search_fn=fetch_search_html):
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 500:
        raise ValueError("Research topic must be 1–500 characters.")
    terms = queries or [
        topic.strip(),
        topic.strip() + " official documentation",
        topic.strip() + " research data independent analysis",
    ]
    terms = [str(q).strip()[:400] for q in terms if str(q).strip()][:5]
    all_results, seen = [], set()
    errors = []
    for term in terms:
        try:
            found = parse_results(search_fn(term), term, max_results=max_results)
        except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
            errors.append({"query": term, "error_type": type(exc).__name__, "error": str(exc)[:250]})
            continue
        for result in found:
            if result["url"] not in seen:
                seen.add(result["url"])
                all_results.append(result)
    if not all_results:
        raise RuntimeError("No search results were collected. Check connectivity or try supplied source notes. " +
                           ("Last error: " + errors[-1]["error"] if errors else "The search engine returned no parseable results."))
    metadata = {
        "topic": topic.strip(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "engine": "DuckDuckGo HTML (no API key)",
        "queries": terms,
        "result_count": len(all_results),
        "search_errors": errors,
        "verified": False,
        "note": "Search titles/snippets are discovery leads. Open and verify the linked sources before using factual claims.",
    }
    return metadata, all_results


def render_markdown(metadata, results):
    lines = [
        "# Research leads: " + metadata["topic"], "",
        "- Collected: " + metadata["collected_at"],
        "- Search engine: " + metadata["engine"],
        "- Results: " + str(metadata["result_count"]),
        "- Independently verified: no",
        "",
        "> These are discovery leads, not proof. Open primary sources, check dates and context, and record the evidence supporting each factual claim.",
        "",
    ]
    for index, item in enumerate(results, start=1):
        lines.extend([
            "## [S" + str(index) + "] " + item["title"],
            "- URL: " + item["url"],
            "- Search query: " + item["query"],
            "- Search snippet: " + (item["snippet"] or "(No snippet was returned.)"),
            "",
        ])
    if metadata["search_errors"]:
        lines.extend(["## Partial search warnings", ""])
        for error in metadata["search_errors"]:
            lines.append("- " + error["query"] + ": " + error["error_type"] + " — " + error["error"])
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--out", default="workspace/research/latest.md")
    parser.add_argument("--max-results", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.max_results <= 15:
        raise SystemExit("--max-results must be between 1 and 15.")
    output = Path(args.out).expanduser()
    output = output.resolve() if output.is_absolute() else (ROOT / output).resolve()
    if output == WORKSPACE or WORKSPACE not in output.parents:
        raise SystemExit("Research output must remain inside the project workspace.")
    try:
        metadata, results = research(args.query, max_results=args.max_results)
    except (ValueError, RuntimeError, OSError, urllib.error.URLError) as exc:
        raise SystemExit("Research failed: " + str(exc))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(metadata, results), encoding="utf-8")
    output.with_suffix(".json").write_text(json.dumps({"metadata": metadata, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Collected", len(results), "search leads.")
    print("Markdown:", output)
    print("JSON:", output.with_suffix(".json"))
    print("No result was independently fact-checked.")


if __name__ == "__main__":
    main()
