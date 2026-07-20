"""
FastAPI backend + scheduler.

  GET  /              -> the dashboard (static/index.html)
  GET  /api/top-news  -> current top N stories with scores + ad copy
  GET  /api/status    -> last/next refresh, counts, whether Gemini is wired up
  POST /api/refresh   -> trigger a refresh now (runs in the background)

A background scheduler runs the pipeline on startup and then every
REFRESH_HOURS, so the feed "syncs with real-time news" on its own.

Run:  python app.py    (or:  uvicorn app:app --reload)
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler

import db
import gemini_client
from config import BASE_DIR, TOP_N, TOP_PER_NICHE, REFRESH_HOURS, NEWS_SCOPE, GEMINI_MODEL
from pipeline import run_pipeline

scheduler = BackgroundScheduler(timezone="UTC")
_next_run = {"at": None}


def _scheduled_job():
    print(f"[scheduler] running pipeline @ {datetime.now(timezone.utc).isoformat()}")
    result = run_pipeline()
    print(f"[scheduler] {result}")
    _next_run["at"] = (datetime.now(timezone.utc)
                       + timedelta(hours=REFRESH_HOURS)).isoformat()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # initial run on startup (in scheduler thread so server starts immediately)
    scheduler.add_job(_scheduled_job, "date",
                      run_date=datetime.now(timezone.utc) + timedelta(seconds=2))
    scheduler.add_job(_scheduled_job, "interval", hours=REFRESH_HOURS,
                      id="refresh", max_instances=1)
    scheduler.start()
    _next_run["at"] = (datetime.now(timezone.utc)
                       + timedelta(hours=REFRESH_HOURS)).isoformat()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="NotifAI", lifespan=lifespan)


@app.get("/api/top-news")
def top_news(niche: str | None = None):
    if niche and niche != "all":
        return {"top": db.get_by_niche(niche, TOP_PER_NICHE),
                "count": TOP_PER_NICHE, "niche": niche}
    return {"top": db.get_top(TOP_N), "count": TOP_N, "niche": "all"}


@app.get("/api/niches")
def niches():
    return {"niches": db.get_niche_list()}

@app.get("/api/status")
def status():
    s = db.get_status()
    return {
        **s,
        "next_run": _next_run["at"],
        "refresh_hours": REFRESH_HOURS,
        "news_scope": NEWS_SCOPE,
        "gemini_enabled": gemini_client.available(),
        "gemini_model": GEMINI_MODEL if gemini_client.available() else None,
    }


@app.post("/api/refresh")
def refresh(background_tasks: BackgroundTasks):
    background_tasks.add_task(_scheduled_job)
    return JSONResponse({"status": "refresh started"})


@app.get("/")
def home():
    return FileResponse(str(BASE_DIR / "static" / "index.html"))


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


if __name__ == "__main__":
    import os, uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
