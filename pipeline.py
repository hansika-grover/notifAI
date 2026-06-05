"""
The pipeline: fetch -> score virality -> pick top N -> correlate to niche
-> generate ad copy -> store. This is what the scheduler runs every REFRESH_HOURS
("sync with real-time news").
"""
from datetime import datetime, timezone

import db
from config import TOP_N
from news_fetcher import fetch_all
from virality import score_batch
from correlator import correlate

import re
from difflib import SequenceMatcher


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (t or "").lower())


def _pick_diverse_top(scored: list[dict], n: int) -> list[dict]:
    """Take the top n by score, skipping near-duplicate stories so the
    same event from different outlets doesn't fill the list."""
    top = []
    for a in scored:
        if any(SequenceMatcher(None, _norm(a['title']), _norm(t['title'])).ratio() > 0.72
               for t in top):
            continue
        top.append(a)
        if len(top) >= n:
            break
    return top

_running = False  # simple guard so two runs never overlap


def run_pipeline() -> dict:
    global _running
    if _running:
        return {"status": "skipped", "reason": "a refresh is already running"}
    _running = True

    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started = datetime.now(timezone.utc).isoformat()
    db.init_db()
    db.start_run(batch_id, started)

    try:
        # 1. fetch live news
        articles = fetch_all()

        # 2. score virality (transparent heuristic)
        articles = score_batch(articles)

        # 3. rank, take the top N of this batch
        articles.sort(key=lambda a: a["virality_score"], reverse=True)
        top = _pick_diverse_top(articles, TOP_N)

        # 4. correlate ONLY the top stories to a niche + write ad copy
        #    (keeps Gemini calls tiny -> well within the free tier)
        for a in top:
            correlate(a)

        # 5. persist everything; flag the current top N
        db.clear_top_flags()
        top_ids = {a["id"] for a in top}
        for a in articles:
            a.setdefault("niche", None)
            a.setdefault("niche_label", None)
            a.setdefault("niche_relevance", 0.0)
            a.setdefault("ad_relevant", 0)
            a.setdefault("ad_headline", None)
            a.setdefault("ad_description", None)
            a.setdefault("ad_reason", "")
            a["batch_id"] = batch_id
            a["is_top"] = 1 if a["id"] in top_ids else 0
            db.upsert_article(a)

        finished = datetime.now(timezone.utc).isoformat()
        db.finish_run(batch_id, finished, len(articles), len(top), "done")
        return {"status": "done", "batch_id": batch_id,
                "fetched": len(articles), "top": len(top)}

    except Exception as e:
        db.finish_run(batch_id, datetime.now(timezone.utc).isoformat(),
                      0, 0, "error", str(e))
        return {"status": "error", "error": str(e)}
    finally:
        _running = False


if __name__ == "__main__":
    import json
    print(json.dumps(run_pipeline(), indent=2))
    print("\nTop stories now in the dashboard store:\n")
    for a in db.get_top(TOP_N):
        print(f"{a['virality_score']:5.1f}  [{a['source']}] {a['title']}")
        print(f"        niche: {a['niche_label']}  (rel {a['niche_relevance']})")
        print(f"        ad: {a['ad_headline']} | {a['ad_description']}\n")