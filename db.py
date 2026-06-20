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
                creatives       TEXT,
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
        cols = [r["name"] for r in con.execute("PRAGMA table_info(articles)").fetchall()]
        if "creatives" not in cols:
            con.execute("ALTER TABLE articles ADD COLUMN creatives TEXT")


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
               ad_relevant,ad_headline,ad_description,ad_reason,creatives,is_top)
            VALUES
              (:id,:title,:url,:source,:summary,:published,:fetched_at,:batch_id,
               :virality_score,:virality_parts,:niche,:niche_label,:niche_relevance,
               :ad_relevant,:ad_headline,:ad_description,:ad_reason,:creatives,:is_top)
            ON CONFLICT(id) DO UPDATE SET
               title=excluded.title, summary=excluded.summary,
               fetched_at=excluded.fetched_at, batch_id=excluded.batch_id,
               virality_score=excluded.virality_score,
               virality_parts=excluded.virality_parts,
               niche=excluded.niche, niche_label=excluded.niche_label,
               niche_relevance=excluded.niche_relevance,
               ad_relevant=excluded.ad_relevant, ad_headline=excluded.ad_headline,
               ad_description=excluded.ad_description, ad_reason=excluded.ad_reason,
               creatives=excluded.creatives, is_top=excluded.is_top
            """,
            {**a, "virality_parts": json.dumps(a.get("virality_parts", {})),
             "creatives": json.dumps(a.get("creatives") or {})},
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
    try:
        d["creatives"] = json.loads(d.get("creatives") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["creatives"] = {}
    return d


def get_by_niche(niche: str, limit=5):
    """Top `limit` stories for one niche from the latest completed batch."""
    with _conn() as con:
        bid = latest_batch_id()
        if not bid:
            return []
        rows = con.execute(
            "SELECT * FROM articles WHERE batch_id=? AND niche=? "
            "ORDER BY virality_score DESC LIMIT ?",
            (bid, niche, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_niche_list():
    """Niches present in the latest batch, with story counts (for filter chips)."""
    with _conn() as con:
        bid = latest_batch_id()
        if not bid:
            return []
        rows = con.execute(
            "SELECT niche, niche_label, COUNT(*) c FROM articles "
            "WHERE batch_id=? AND niche IS NOT NULL "
            "GROUP BY niche, niche_label ORDER BY c DESC",
            (bid,),
        ).fetchall()
        return [{"niche": r["niche"], "label": r["niche_label"], "count": r["c"]}
                for r in rows]