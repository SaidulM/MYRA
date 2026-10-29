"""MYRA web research engine.

This is intentionally dependency-light and works with the Python standard
library: search public results, fetch a bounded number of pages, extract
readable text and produce a cited report.  If an AI summarizer callback is
provided it writes the synthesis; otherwise MYRA returns a transparent
extractive report instead of pretending an AI summary happened.
"""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from html.parser import HTMLParser


USER_AGENT = "MYRA/3.0 research (local personal assistant)"
MAX_FETCH_BYTES = 1_500_000


class ResearchError(Exception):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    engine: str = ""


def _clean(value, limit=500):
    return " ".join(html.unescape(str(value or "")).split())[:limit]


def validate_public_url(url, *, resolve_dns=False):
    url = str(url or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ResearchError("Only complete public http/https URLs are allowed.")
    host = parsed.hostname.lower().strip(".")
    if host in {"localhost"} or host.endswith((".local", ".localhost")):
        raise ResearchError("Local/private network URLs are not allowed in web research.")

    def reject_ip(value):
        ip = ipaddress.ip_address(value)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ResearchError("Local/private network URLs are not allowed in web research.")

    try:
        reject_ip(host)
    except ValueError:
        pass
    if resolve_dns:
        try:
            for info in socket.getaddrinfo(host, 443 if parsed.scheme == "https" else 80):
                reject_ip(info[4][0])
        except ResearchError:
            raise
        except OSError:
            # The fetch itself will return a clear network error.
            pass
    return url


def _open(url, opener=None, timeout=12):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.8"})
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=timeout) as response:
        content_type = ""
        try:
            content_type = response.headers.get_content_type()
        except Exception:
            content_type = (response.headers.get("Content-Type", "") if getattr(response, "headers", None) else "").split(";")[0]
        body = response.read(MAX_FETCH_BYTES + 1)
        if len(body) > MAX_FETCH_BYTES:
            body = body[:MAX_FETCH_BYTES]
        charset = "utf-8"
        try:
            charset = response.headers.get_content_charset() or charset
        except Exception:
            pass
        return body.decode(charset, errors="replace"), content_type, getattr(response, "url", url)


class _DuckParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._capture = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "a" and "result__a" in classes:
            self._current = {"title": "", "url": attrs.get("href", ""), "snippet": ""}
            self._capture = "title"
            self.results.append(self._current)
        elif tag == "a" and "result__snippet" in classes and self.results:
            self._current = self.results[-1]
            self._capture = "snippet"

    def handle_data(self, data):
        if self._current is not None and self._capture:
            self._current[self._capture] += data

    def handle_endtag(self, tag):
        if tag == "a":
            self._capture = None


def _duck_url(raw):
    raw = html.unescape(raw or "")
    if raw.startswith("//"):
        raw = "https:" + raw
    parsed = urllib.parse.urlparse(raw)
    if "duckduckgo.com" in (parsed.hostname or ""):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return urllib.parse.unquote(target)
    return raw


def search_duckduckgo(query, max_results=5, opener=None):
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    text, _ctype, _final = _open(url, opener=opener, timeout=12)
    parser = _DuckParser()
    parser.feed(text)
    out, seen = [], set()
    for item in parser.results:
        target = _duck_url(item.get("url", ""))
        try:
            validate_public_url(target)
        except ResearchError:
            continue
        if target in seen:
            continue
        seen.add(target)
        title = _clean(item.get("title"), 220)
        if title:
            out.append(SearchResult(title, target, _clean(item.get("snippet"), 500), "duckduckgo"))
        if len(out) >= max_results:
            break
    return out


def search_bing_rss(query, max_results=5, opener=None):
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "format": "rss"})
    text, _ctype, _final = _open(url, opener=opener, timeout=12)
    root = ET.fromstring(text.encode("utf-8"))
    out, seen = [], set()
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title", ""), 220)
        target = _clean(item.findtext("link", ""), 2000)
        snippet = _clean(item.findtext("description", ""), 500)
        try:
            validate_public_url(target)
        except ResearchError:
            continue
        if title and target and target not in seen:
            seen.add(target)
            out.append(SearchResult(title, target, snippet, "Bing"))
        if len(out) >= max_results:
            break
    return out


def search_web(query, max_results=5, opener=None):
    query = _clean(query, 300)
    if not query:
        raise ResearchError("Research query is required.")
    max_results = max(1, min(int(max_results or 5), 10))
    errors = []
    for engine in (search_duckduckgo, search_bing_rss):
        try:
            results = engine(query, max_results=max_results, opener=opener)
            if results:
                return results
        except Exception as exc:
            errors.append(f"{engine.__name__}: {exc.__class__.__name__}")
    raise ResearchError("No public search results could be retrieved. " + "; ".join(errors))


_SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "form", "button", "nav", "footer", "header", "aside"}
_BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "blockquote", "pre"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.blocks = []
        self._skip = 0
        self._in_title = False
        self._block = None

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in _BLOCK_TAGS and not self._skip:
            self._block = []

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in _BLOCK_TAGS and self._block is not None:
            text = _clean(" ".join(self._block), 1200)
            if len(text) >= 35:
                self.blocks.append(text)
            self._block = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip and self._block is not None:
            self._block.append(data)


def extract_readable_text(document, content_type="text/html", max_chars=9000):
    if "xml" in content_type or document.lstrip().startswith("<?xml"):
        # Avoid treating feeds as article HTML; strip tags conservatively.
        text = re.sub(r"<[^>]+>", " ", document)
        return {"title": "", "text": _clean(text, max_chars)}
    if "html" not in content_type and "<html" not in document[:1000].lower():
        return {"title": "", "text": _clean(document, max_chars)}
    parser = _TextExtractor()
    parser.feed(document)
    chunks, seen, total = [], set(), 0
    for block in parser.blocks:
        key = block.casefold()
        if key in seen:
            continue
        seen.add(key)
        chunks.append(block)
        total += len(block)
        if total >= max_chars:
            break
    return {"title": _clean(parser.title, 220), "text": "\n".join(chunks)[:max_chars]}


def fetch_page(url, opener=None, resolve_dns=True):
    url = validate_public_url(url, resolve_dns=resolve_dns)
    started = time.monotonic()
    document, content_type, final_url = _open(url, opener=opener, timeout=15)
    extracted = extract_readable_text(document, content_type=content_type)
    return {
        "url": final_url,
        "title": extracted.get("title") or final_url,
        "text": extracted.get("text") or "",
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def _extractive_report(query, sources):
    lines = [f"Research results for: {query}", "", "Source excerpts (no AI synthesis was available):"]
    for index, source in enumerate(sources, 1):
        lines.append(f"\n[{index}] {source.get('title') or source['url']}")
        excerpt = _clean(source.get("text") or source.get("snippet"), 900)
        if excerpt:
            lines.append(excerpt)
        lines.append(source["url"])
    return "\n".join(lines)


def research(query, max_sources=5, opener=None, summarizer=None, resolve_dns=True):
    """Search, fetch and synthesize a cited report within hard bounds."""
    query = _clean(query, 300)
    if not query:
        raise ResearchError("Research query is required.")
    max_sources = max(1, min(int(max_sources or 5), 8))
    results = search_web(query, max_results=max_sources, opener=opener)
    sources, errors = [], []
    for result in results:
        try:
            page = fetch_page(result.url, opener=opener, resolve_dns=resolve_dns)
            sources.append({
                "title": page.get("title") or result.title,
                "url": page.get("url") or result.url,
                "snippet": result.snippet,
                "text": page.get("text") or result.snippet,
                "engine": result.engine,
            })
        except Exception as exc:
            errors.append({"url": result.url, "error": f"{exc.__class__.__name__}: {exc}"[:300]})
            sources.append({**asdict(result), "text": result.snippet})
    report = ""
    synthesized = False
    if summarizer:
        try:
            report = str(summarizer(query, sources) or "").strip()
            synthesized = bool(report)
        except Exception as exc:
            errors.append({"stage": "synthesis", "error": f"{exc.__class__.__name__}: {exc}"[:300]})
    if not report:
        report = _extractive_report(query, sources)
    citations = [{"index": i + 1, "title": s.get("title"), "url": s.get("url")} for i, s in enumerate(sources)]
    return {
        "ok": True,
        "query": query,
        "report": report,
        "sources": [{k: source.get(k) for k in ("title", "url", "snippet", "engine")} for source in sources],
        "source_excerpts": [source.get("text", "")[:1200] for source in sources],
        "citations": citations,
        "synthesized_by_ai": synthesized,
        "errors": errors,
        "verified": bool(sources),
    }
