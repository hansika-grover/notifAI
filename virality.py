"""
Virality scorer -- transparent heuristic, no ML model, no network, instant.

Design goals you asked for:
  * "efficient"          -> pure Python + a tiny sentiment lexicon, runs in ms.
  * "no false virality"  -> every sub-signal is bounded and capped, so no single
                            clickbait trick can spike a score. Each story returns
                            a full breakdown so nothing is a black box.

Final score = 0..100, a weighted blend of grounded signals:

  topic_heat   0.35  how many OTHER stories this batch cover the same thing
                     (real cross-outlet traction -> the strongest real signal)
  recency      0.15  newer stories decay slower
  sentiment    0.20  emotional intensity |compound| (research links this to sharing)
  triggers     0.15  numbers / questions / curiosity & emotion words (CAPPED)
  source_reach 0.15  small curated tier map for major US outlets
"""
import math
import re
from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_VADER = SentimentIntensityAnalyzer()

WEIGHTS = {
    "topic_heat": 0.35,
    "recency": 0.15,
    "sentiment": 0.20,
    "triggers": 0.15,
    "source_reach": 0.15,
}

# Curiosity / emotion trigger words (kept small + capped so it can't dominate)
TRIGGER_WORDS = {
    "shocking", "surge", "soar", "soared", "crash", "plunge", "warning", "warn",
    "crisis", "record", "boom", "collapse", "skyrocket", "slash", "slashed",
    "exclusive", "revealed", "breaking", "urgent", "danger", "fear", "fears",
    "alarm", "scramble", "spike", "free", "save", "win", "lose", "loses",
}

# Light reputational tiers for common US outlets -> reach proxy (0..1)
SOURCE_TIER = {
    1.0: {"reuters", "associated press", "ap", "the new york times", "nyt",
          "the washington post", "wall street journal", "wsj", "cnn", "cnbc",
          "bbc", "bloomberg", "npr", "abc news", "nbc news", "cbs news", "usa today"},
    0.75: {"fox news", "forbes", "business insider", "the hill", "axios",
           "politico", "the guardian", "marketwatch", "yahoo", "msnbc"},
    0.55: {"newsweek", "the verge", "techcrunch", "fortune", "time"},
}

_STOP = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "as", "at", "by", "from", "is", "are", "was", "were", "be", "this", "that",
    "it", "its", "your", "you", "how", "what", "why", "after", "amid", "over",
    "into", "out", "new", "says", "could", "will", "than", "more", "most",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _recency_score(published_iso: str) -> float:
    try:
        pub = datetime.fromisoformat(published_iso)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return 0.5
    hours = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
    hours = max(hours, 0)
    # half-life ~18h: 1.0 now -> ~0.5 at 18h -> ~0.25 at 36h
    return round(math.exp(-hours / 26.0), 4)


def _sentiment_score(text: str) -> float:
    return round(abs(_VADER.polarity_scores(text)["compound"]), 4)


def _trigger_score(title: str) -> float:
    toks = set(re.findall(r"[a-z']+", title.lower()))
    hits = len(toks & TRIGGER_WORDS)
    has_number = 1 if re.search(r"\d", title) else 0
    has_q = 1 if "?" in title else 0
    raw = 0.30 * min(hits, 3) / 3 + 0.40 * has_number + 0.30 * has_q
    return round(min(raw, 1.0), 4)  # hard cap at 1.0


def _source_score(source: str) -> float:
    s = (source or "").lower().strip()
    for val, names in SOURCE_TIER.items():
        if any(n == s or n in s for n in names):
            return val
    return 0.40  # unknown / local outlet -> modest baseline, not zero


def _topic_heat(article: dict, all_tokens: list[set[str]], idx: int) -> float:
    """Real cross-outlet traction: how many other stories share >=2 key tokens."""
    mine = all_tokens[idx]
    if not mine:
        return 0.0
    overlaps = 0
    for j, other in enumerate(all_tokens):
        if j == idx or not other:
            continue
        if len(mine & other) >= 2:
            overlaps += 1
    # normalize: 0 overlaps -> 0, saturates around 6 corroborating stories
    return round(min(overlaps / 6.0, 1.0), 4)


def score_batch(articles: list[dict]) -> list[dict]:
    """Adds 'virality_score' (0..100) and 'virality_parts' to each article."""
    all_tokens = [_tokens(f"{a.get('title','')} {a.get('summary','')}") for a in articles]

    for i, a in enumerate(articles):
        title = a.get("title", "")
        text = f"{title} {a.get('summary','')}"
        parts = {
            "topic_heat": _topic_heat(a, all_tokens, i),
            "recency": _recency_score(a.get("published", "")),
            "sentiment": _sentiment_score(text),
            "triggers": _trigger_score(title),
            "source_reach": _source_score(a.get("source", "")),
        }
        blended = sum(parts[k] * WEIGHTS[k] for k in WEIGHTS)
        a["virality_score"] = round(blended * 100, 1)
        a["virality_parts"] = {k: round(v, 3) for k, v in parts.items()}
    return articles


if __name__ == "__main__":
    from news_fetcher import fetch_all
    arts = score_batch(fetch_all())
    arts.sort(key=lambda x: x["virality_score"], reverse=True)
    print("Top 5 by virality:\n")
    for a in arts[:5]:
        print(f"{a['virality_score']:5.1f}  [{a['source']}] {a['title']}")
        print(f"        {a['virality_parts']}")
