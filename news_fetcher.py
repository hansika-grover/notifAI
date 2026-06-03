"""
Multi-source news fetching -- keyless & free by default.

Sources (toggle in config.py):
  * Google News RSS   -- one search feed per niche (already on-topic).
  * Publisher RSS     -- CNBC, Yahoo Finance, NPR, HousingWire, Insurance
                         Journal, etc. These are general finance/housing feeds,
                         so each item is PREFILTERED to your niche keywords
                         before being kept.
  * NewsData.io       -- optional free-tier API, only if NEWSDATA_API_KEY is set.

Why multi-source helps: the virality "topic_heat" signal rewards stories covered
by many outlets. Pulling the same event from several independent sources is real
cross-outlet corroboration, which sharpens that score.

Every source returns the SAME normalized dict, so nothing downstream changes:
  {id, title, url, source, summary, published, fetched_at, query_niche}
"""
import re
import time
import urllib.parse
from datetime import datetime, timezone

import feedparser

from config import (
    NICHES, LANG, CEID, MAX_PER_QUERY, MAX_PER_FEED, NEWS_SCOPE,
    USE_GOOGLE_NEWS, USE_PUBLISHER_RSS, PUBLISHER_FEEDS, NEWSDATA_API_KEY,
)
from db import article_id

RSS_SEARCH = "https://news.google.com/rss/search?q={q}&hl={hl}&gl=US&ceid={ceid}"
RSS_TOP = "https://news.google.com/rss?hl={hl}&gl=US&ceid={ceid}"

# Flat set of every niche keyword, used to prefilter general publisher feeds.
_ALL_KEYWORDS = sorted(
    {kw for cfg in NICHES.values() for kw in (cfg["strong"] + cfg["weak"])},
    key=len, reverse=True,
)


def _matches_any_niche(text: str) -> bool:
    low = text.lower()
    return any(re.search(r"\b" + re.escape(kw) + r"\b", low) for kw in _ALL_KEYWORDS)


def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (t or "").lower())).strip()


def _strip_html(s: str) -> str:
    if "<" in s:
        s = re.sub(r"<[^>]+>", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
    return s


def _published_iso(entry) -> str:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc).isoformat()
    return datetime.now(timezone.utc).isoformat()


def _gn_source(entry) -> str:
    if getattr(entry, "source", None) and getattr(entry.source, "title", None):
        return entry.source.title
    title = entry.get("title", "")
    return title.rsplit(" - ", 1)[-1].strip() if " - " in title else ""


def _gn_title(entry) -> str:
    title = entry.get("title", "").strip()
    src = _gn_source(entry)
    if src and title.endswith(f" - {src}"):
        title = title[: -(len(src) + 3)].strip()
    return title


def _mk(title, url, source, summary, published, niche_key) -> dict:
    return {
        "id": article_id(url),
        "title": title,
        "url": url,
        "source": source,
        "summary": (summary or "")[:600],
        "published": published,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "query_niche": niche_key,
    }


# --------------------------------------------------------------------------- #
#  Individual sources (each yields normalized dicts)                          #
# --------------------------------------------------------------------------- #
def _google_news():
    feeds = [(RSS_SEARCH.format(q=urllib.parse.quote(cfg["query"]), hl=LANG, ceid=CEID), key)
             for key, cfg in NICHES.items()]
    if NEWS_SCOPE == "general":
        feeds.append((RSS_TOP.format(hl=LANG, ceid=CEID), None))
    for url, niche_key in feeds:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:MAX_PER_QUERY]:
                link = e.get("link", "")
                if not link:
                    continue
                yield _mk(_gn_title(e), link, _gn_source(e),
                          _strip_html(e.get("summary", "")), _published_iso(e), niche_key)
        except Exception as ex:
            print(f"[fetch] google-news feed failed ({niche_key}): {ex}")
        time.sleep(0.3)


def _publisher_rss():
    for url, name in PUBLISHER_FEEDS:
        try:
            f = feedparser.parse(url)
            for e in f.entries[:MAX_PER_FEED]:
                link = e.get("link", "")
                title = e.get("title", "").strip()
                if not link or not title:
                    continue
                summary = _strip_html(e.get("summary", ""))
                if not _matches_any_niche(f"{title} {summary}"):
                    continue  # keep publisher feeds on-niche
                yield _mk(title, link, name, summary, _published_iso(e), None)
        except Exception as ex:
            print(f"[fetch] publisher feed failed ({name}): {ex}")
        time.sleep(0.3)


def _newsdata():
    """Optional free-tier API. Off unless NEWSDATA_API_KEY is set."""
    if not NEWSDATA_API_KEY:
        return
    import requests
    queries = [cfg["query"] for cfg in NICHES.values()]
    for q in queries:
        try:
            r = requests.get(
                "https://newsdata.io/api/1/news",
                params={"apikey": NEWSDATA_API_KEY, "q": q,
                        "country": "us", "language": "en"},
                timeout=20,
            )
            if r.status_code != 200:
                print(f"[fetch] newsdata HTTP {r.status_code}")
                continue
            for it in (r.json().get("results") or [])[:MAX_PER_QUERY]:
                link = it.get("link", "")
                title = (it.get("title") or "").strip()
                if not link or not title:
                    continue
                pub = it.get("pubDate")
                try:
                    pub_iso = datetime.fromisoformat(pub).replace(
                        tzinfo=timezone.utc).isoformat() if pub else _published_iso({})
                except ValueError:
                    pub_iso = datetime.now(timezone.utc).isoformat()
                yield _mk(title, link, it.get("source_id", "NewsData"),
                          it.get("description", ""), pub_iso, None)
        except Exception as ex:
            print(f"[fetch] newsdata query failed: {ex}")
        time.sleep(0.5)


# --------------------------------------------------------------------------- #
#  Merge + dedupe                                                             #
# --------------------------------------------------------------------------- #
def fetch_all() -> list[dict]:
    """Pull every enabled source, dedupe by URL and by exact title."""
    seen_ids, seen_titles, articles = set(), set(), []

    def add(art):
        nt = _norm_title(art["title"])
        if not nt or art["id"] in seen_ids or nt in seen_titles:
            return
        seen_ids.add(art["id"])
        seen_titles.add(nt)
        articles.append(art)

    if USE_GOOGLE_NEWS:
        for art in _google_news():
            add(art)
    if USE_PUBLISHER_RSS:
        for art in _publisher_rss():
            add(art)
    if NEWSDATA_API_KEY:
        for art in _newsdata():
            add(art)

    return articles


if __name__ == "__main__":
    arts = fetch_all()
    print(f"Fetched {len(arts)} unique articles")
    from collections import Counter
    by_src = Counter(a["source"] for a in arts)
    print("By source:", dict(by_src.most_common(12)))
    for a in arts[:6]:
        print(f" - [{a['source']}] {a['title'][:70]}")