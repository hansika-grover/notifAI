"""
Tiny SQLite layer. One file (news.db), no server, no setup.
Stores every fetched article + its scores, and marks the current top N.
"""
import json
import sqlite3
import hashlib
from contextlib import contextmanager
from config import DB_PATH


def article_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id              TEXT PRIMARY KEY,
                title           TEXT,
                url             TEXT,
                source          TEXT,
                summary         TEXT,
                published       TEXT,
                fetched_at      TEXT,
                batch_id        TEXT,
                virality_score  REAL,
                virality_parts  TEXT,
                niche           TEXT,
                niche_label     TEXT,
                niche_relevance REAL,
                ad_relevant     INTEGER DEFAULT 0,
                ad_headline     TEXT,
                ad_description  TEXT,
                ad_reason       TEXT,
                is_top          INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS runs (
                batch_id    TEXT PRIMARY KEY,
                started_at  TEXT,
                finished_at TEXT,
                n_fetched   INTEGER,
                n_top       INTEGER,
                status      TEXT,
                note        TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_articles_batch ON articles(batch_id);
            CREATE INDEX IF NOT EXISTS idx_articles_top   ON articles(is_top);
            """
        )


def start_run(batch_id: str, started_at: str):
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO runs (batch_id, started_at, status) VALUES (?,?,?)",
            (batch_id, started_at, "running"),
        )


def finish_run(batch_id, finished_at, n_fetched, n_top, status, note=""):
    with _conn() as con:
        con.execute(
            """UPDATE runs SET finished_at=?, n_fetched=?, n_top=?, status=?, note=?
               WHERE batch_id=?""",
            (finished_at, n_fetched, n_top, status, note, batch_id),
        )


def upsert_article(a: dict):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO articles
              (id,title,url,source,summary,published,fetched_at,batch_id,
               virality_score,virality_parts,niche,niche_label,niche_relevance,
               ad_relevant,ad_headline,ad_description,ad_reason,is_top)
            VALUES
              (:id,:title,:url,:source,:summary,:published,:fetched_at,:batch_id,
               :virality_score,:virality_parts,:niche,:niche_label,:niche_relevance,
               :ad_relevant,:ad_headline,:ad_description,:ad_reason,:is_top)
            ON CONFLICT(id) DO UPDATE SET
               title=excluded.title, summary=excluded.summary,
               fetched_at=excluded.fetched_at, batch_id=excluded.batch_id,
               virality_score=excluded.virality_score,
               virality_parts=excluded.virality_parts,
               niche=excluded.niche, niche_label=excluded.niche_label,
               niche_relevance=excluded.niche_relevance,
               ad_relevant=excluded.ad_relevant, ad_headline=excluded.ad_headline,
               ad_description=excluded.ad_description, ad_reason=excluded.ad_reason,
               is_top=excluded.is_top
            """,
            {**a, "virality_parts": json.dumps(a.get("virality_parts", {}))},
        )


def clear_top_flags():
    with _conn() as con:
        con.execute("UPDATE articles SET is_top=0")


def latest_batch_id():
    with _conn() as con:
        row = con.execute(
            "SELECT batch_id FROM runs WHERE status='done' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return row["batch_id"] if row else None


def get_top(limit=5):
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM articles WHERE is_top=1 ORDER BY virality_score DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_status():
    with _conn() as con:
        run = con.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        total = con.execute("SELECT COUNT(*) c FROM articles").fetchone()["c"]
        return {
            "last_run": dict(run) if run else None,
            "total_articles_stored": total,
        }


def _row_to_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    try:
        d["virality_parts"] = json.loads(d.get("virality_parts") or "{}")
    except json.JSONDecodeError:
        d["virality_parts"] = {}
    return d
