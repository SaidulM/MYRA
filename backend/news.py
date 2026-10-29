"""MYRA — World Monitor News Feed Engine (Stage 10).

Fetches live headlines from public RSS feeds using only Python's
standard library and caches them locally so they are accessible offline.
"""
from __future__ import annotations

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List
from urllib.request import Request, urlopen

def _safe_urlopen(req, timeout=7):
    # Verified TLS only.  Offline/error cases fall back to the disk cache.
    return urlopen(req, timeout=timeout)

import paths

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = paths.data_dir(create=False)
CACHE_FILE = DATA_DIR / "news_cache.json"

FEEDS = [
    {
        "name": "BBC World News",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "region": "global",
    },
    {
        "name": "Al Jazeera English",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "region": "mideast",
    },
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "region": "tech",
    },
    {
        "name": "NDTV World",
        "url": "https://feeds.feedburner.com/ndtvnews-world-news",
        "region": "asia",
    },
]

_MEM_CACHE: Dict[str, Any] = {"items": [], "updated_at": 0}


def _fetch_feed(url: str, source_name: str, region: str) -> List[Dict[str, str]]:
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MYRA/1.0"}
    try:
        req = Request(url, headers=headers)
        with _safe_urlopen(req, timeout=7) as resp:
            content = resp.read()
        root = ET.fromstring(content)
        # Handle standard RSS 2.0
        for item in root.findall(".//item")[:10]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            description = item.findtext("description", "").strip()
            # Clean HTML tags in description if any
            if "<" in description and ">" in description:
                try:
                    desc_root = ET.fromstring(f"<root>{description}</root>")
                    description = "".join(desc_root.itertext())
                except Exception:
                    pass

            if title:
                items.append({
                    "title": title,
                    "link": link,
                    "source": source_name,
                    "region": region,
                    "time": pub_date,
                    "snippet": description[:200] if description else "",
                })
    except Exception:
        pass
    return items


def get_news(region: str = "all", force_refresh: bool = False) -> Dict[str, Any]:
    """Retrieve news headlines. Uses cache if recent or offline."""
    global _MEM_CACHE
    now = time.time()

    # Load from disk cache if memory cache is empty
    if not _MEM_CACHE["items"] and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _MEM_CACHE = json.load(f)
        except Exception:
            pass

    # If cache is older than 15 minutes or force_refresh, fetch new
    if force_refresh or (now - _MEM_CACHE.get("updated_at", 0) > 900) or not _MEM_CACHE["items"]:
        all_items = []
        for f in FEEDS:
            feed_items = _fetch_feed(f["url"], f["name"], f["region"])
            all_items.extend(feed_items)

        if all_items:
            _MEM_CACHE = {
                "items": all_items,
                "updated_at": int(now),
            }
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                with open(CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(_MEM_CACHE, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    items = _MEM_CACHE.get("items", [])
    if region and region != "all":
        items = [i for i in items if i.get("region") == region]

    return {
        "ok": True,
        "count": len(items),
        "updated_at": _MEM_CACHE.get("updated_at", 0),
        "articles": items,
    }
