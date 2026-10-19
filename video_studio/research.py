#!/usr/bin/env python3
"""Collect free web-search leads without API keys; sources are not automatically verified."""
import argparse
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
import socket
import re
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



MAX_PAGE_BYTES = 1_500_000
MAX_PAGE_TEXT = 12_000


def _host_is_public(host):
    """Reject private, loopback, link-local, reserved, and unresolved hosts."""
    host = (host or "").lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
        except (OSError, ValueError):
            return False
    return bool(addresses) and all(address.is_global for address in addresses)


def _validated_page_url(value):
    url = safe_public_url(value)
    if not url:
        return None
    try:
        host = urllib.parse.urlsplit(url).hostname
    except ValueError:
        return None
    return url if _host_is_public(host) else None


class SafePageRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = _validated_page_url(urllib.parse.urljoin(req.full_url, newurl))
        if not target:
            raise urllib.error.HTTPError(req.full_url, code, "Redirect target rejected by public-host safety checks", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, target)


class PageTextParser(HTMLParser):
    """Extract readable page text while ignoring executable and non-content elements."""
    SKIP = {"script", "style", "noscript", "svg", "canvas", "iframe", "form", "nav", "footer", "header"}
    BLOCK = {"p", "div", "article", "section", "main", "h1", "h2", "h3", "h4", "li", "br", "tr"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.title_depth = 0
        self.in_title = False
        self.title_parts = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self.in_title = True
        if tag in self.SKIP:
            self.skip_depth += 1
        if not self.skip_depth and tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if not self.skip_depth and tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value:
            return
        if self.in_title:
            self.title_parts.append(value)
        if not self.skip_depth:
            self.parts.append(value)

    def result(self):
        title = " ".join(self.title_parts).strip()[:300]
        text = " ".join(" ".join(self.parts).split())[:MAX_PAGE_TEXT]
        return title, text


def fetch_page(url, timeout=12, opener=None):
    """Fetch bounded public HTTP(S) page text. Returns a status object, never raw HTML."""
    validated = _validated_page_url(url)
    if not validated:
        return {"fetch_status": "rejected", "page_title": "", "page_text": "", "fetch_error": "URL or host failed public-address validation"}
    request = urllib.request.Request(
        validated,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8", "Accept-Encoding": "identity"},
        method="GET",
    )
    page_opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), SafePageRedirect())
    try:
        with page_opener.open(request, timeout=max(3, min(int(timeout), 20))) as response:
            final_url = _validated_page_url(response.geturl())
            if not final_url:
                return {"fetch_status": "rejected", "page_title": "", "page_text": "", "fetch_error": "Final URL failed public-address validation"}
            content_type = response.headers.get("Content-Type", "").lower()
            if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
                return {"fetch_status": "skipped_non_text", "page_title": "", "page_text": "", "fetch_error": "Response is not a supported text content type"}
            data = response.read(MAX_PAGE_BYTES + 1)
            if len(data) > MAX_PAGE_BYTES:
                data = data[:MAX_PAGE_BYTES]
                truncated = True
            else:
                truncated = False
            charset = response.headers.get_content_charset() or "utf-8"
            markup = data.decode(charset, errors="replace")
            parser = PageTextParser()
            parser.feed(markup)
            title, text = parser.result()
            if truncated:
                text = text[:MAX_PAGE_TEXT]
            if not text:
                return {"fetch_status": "empty", "page_title": title, "page_text": "", "fetch_error": "No readable page text extracted"}
            return {"fetch_status": "fetched", "page_title": title, "page_text": text, "final_url": final_url, "truncated": truncated}
    except (OSError, ValueError, urllib.error.URLError, TimeoutError, UnicodeError) as exc:
        return {"fetch_status": "failed", "page_title": "", "page_text": "", "fetch_error": type(exc).__name__ + ": " + str(exc)[:180]}


def sanitize_research_query(value):
    """Remove common secrets and direct identifiers before sending task text to a search provider."""
    text = str(value or "")
    patterns = [
        (r"(?i)\b(?:api[_ -]?key|access[_ -]?token|secret|password|passwd|authorization)\b\s*[:=]\s*['\"]?[^\s,'\";]+", "[REDACTED_SECRET]"),
        (r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b", "[REDACTED_TOKEN]"),
        (r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[REDACTED_EMAIL]"),
        (r"(?<!\w)(?:\+?92|0)?3\d{2}[- ]?\d{7}(?!\w)", "[REDACTED_PHONE]"),
        (r"\b\d{5}-\d{7}-\d\b", "[REDACTED_ID_NUMBER]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return " ".join(text.split())[:500]

def research(topic, queries=None, max_results=5, search_fn=fetch_search_html, page_fetch_fn=fetch_page):
    topic = sanitize_research_query(topic)
    if not topic.strip() or len(topic) > 500:
        raise ValueError("Research topic must be 1–500 characters after privacy redaction.")
    terms = queries or [
        topic.strip(),
        topic.strip() + " official documentation",
        topic.strip() + " research data independent analysis",
    ]
    terms = [sanitize_research_query(q)[:400] for q in terms if sanitize_research_query(q)][:5]
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

    # Fetch a bounded, query-diverse set of pages so research does not rely on one search query.
    page_errors = []
    fetch_limit = max(1, min(int(max_results), 8))
    page_targets = []
    selected_urls = set()
    for term in terms:
        match = next((item for item in all_results if item.get("query") == term and item["url"] not in selected_urls), None)
        if match is not None and len(page_targets) < fetch_limit:
            page_targets.append(match)
            selected_urls.add(match["url"])
    for item in all_results:
        if len(page_targets) >= fetch_limit:
            break
        if item["url"] not in selected_urls:
            page_targets.append(item)
            selected_urls.add(item["url"])
    for item in page_targets:
        try:
            page = page_fetch_fn(item["url"])
        except Exception as exc:
            page = {"fetch_status": "failed", "page_title": "", "page_text": "",
                    "fetch_error": type(exc).__name__ + ": " + str(exc)[:180]}
        item.update(page)
        if item.get("fetch_status") != "fetched":
            page_errors.append({"url": item["url"], "status": item.get("fetch_status", "unknown"),
                                "error": item.get("fetch_error", "")[:200]})
        elif item.get("page_title"):
            item["page_title"] = item["page_title"][:300]
        item["page_text"] = str(item.get("page_text", ""))[:MAX_PAGE_TEXT]
    all_results = page_targets + [item for item in all_results if item["url"] not in selected_urls]

    fetched_count = sum(1 for item in all_results if item.get("fetch_status") == "fetched")
    metadata = {
        "topic": topic.strip(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "engine": "DuckDuckGo HTML (no API key)",
        "queries": terms,
        "result_count": len(all_results),
        "pages_attempted": min(len(all_results), max(1, min(int(max_results), 8))),
        "pages_fetched": fetched_count,
        "search_errors": errors,
        "page_errors": page_errors,
        "verified": False,
        "note": "Search leads and page text are collected for analysis, but claims are not independently fact-checked. Check source authority, publication dates, context, and corroboration.",
    }
    return metadata, all_results

def render_markdown(metadata, results):
    lines = [
        "# Research leads: " + metadata["topic"], "",
        "- Collected: " + metadata["collected_at"],
        "- Search engine: " + metadata["engine"],
        "- Search results: " + str(metadata["result_count"]),
        "- Source pages fetched: " + str(metadata.get("pages_fetched", 0)) + "/" + str(metadata.get("pages_attempted", 0)),
        "- Independently verified: no",
        "",
        "> Retrieved page text is evidence to inspect, not automatic proof. Compare primary and independent sources, check dates and context, and attach source URLs to factual claims.",
        "",
    ]
    for index, item in enumerate(results, start=1):
        lines.extend([
            "## [S" + str(index) + "] " + item["title"],
            "- URL: " + item["url"],
            "- Search query: " + item["query"],
            "- Search snippet: " + (item["snippet"] or "(No snippet was returned.)"),
            "- Page fetch status: " + str(item.get("fetch_status", "not_attempted")),
            "- Page title: " + str(item.get("page_title", "")),
            "- Extracted page text: " + (str(item.get("page_text", "")) or "(No page text extracted.)"),
            "",
        ])
    if metadata.get("page_errors"):
        lines.extend(["## Source page fetch warnings", ""])
        for error in metadata["page_errors"]:
            lines.append("- " + error["url"] + ": " + error["status"] + " — " + error.get("error", ""))
        lines.append("")
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
