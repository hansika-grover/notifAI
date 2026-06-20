"""
The pipeline: fetch -> score virality -> pick top N -> correlate to niche
-> generate ad copy -> store. This is what the scheduler runs every REFRESH_HOURS
("sync with real-time news").
"""
from datetime import datetime, timezone

import db
from config import TOP_N, MAX_IMAGES_PER_SYNC, IMAGE_RENDER
from news_fetcher import fetch_all
from virality import score_batch
from correlator import correlate, match_niche, _template_ad
from creatives import make_creatives

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
        articles.sort(key=lambda a: a["virality_score"], reverse=True)

        # 3. niche-match EVERY article (free, lexical) so each niche has a pool.
        #    Matched stories get FREE template copy -- no API calls here.
        for a in articles:
            m = match_niche(a)
            a["niche"] = m["niche"]
            a["niche_label"] = m["niche_label"]
            a["niche_relevance"] = m["niche_relevance"]
            if m["niche"]:
                a.update(_template_ad(a, m))
            else:
                a.update({"ad_relevant": 0, "ad_headline": None,
                          "ad_description": None, "ad_reason": ""})

        # 4. upgrade ONLY the global diverse top to Gemini copy (bounded -> free tier)
        top = _pick_diverse_top(articles, TOP_N)
        for a in top:
            correlate(a)

        # 4b. build creatives (in-context image + video script) for the top.
        #     Image render is capped by MAX_IMAGES_PER_SYNC; scripts are always made.
        rendered = 0
        for a in top:
            if not a.get("niche"):
                continue  # no niche match -> no ad creative
            allow = IMAGE_RENDER != "none" and rendered < MAX_IMAGES_PER_SYNC
            m = {"niche": a.get("niche"), "niche_label": a.get("niche_label")}
            a["creatives"] = make_creatives(a, m, allow_render=allow)
            if a["creatives"].get("image_path"):
                rendered += 1

        # 5. persist everything; flag the current global top
        db.clear_top_flags()
        top_ids = {a["id"] for a in top}
        for a in articles:
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