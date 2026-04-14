"""SQLite storage for dashboard posts."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from src import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    post_id         TEXT NOT NULL,
    etf_code        TEXT NOT NULL,
    etf_name        TEXT NOT NULL,
    title           TEXT DEFAULT '',
    content         TEXT DEFAULT '',
    post_date       TEXT DEFAULT '',
    author          TEXT DEFAULT '',
    likes           INTEGER DEFAULT 0,
    dislikes        INTEGER DEFAULT 0,
    comments        INTEGER DEFAULT 0,
    crawled_at      TEXT NOT NULL,
    UNIQUE(source, post_id, etf_code)
);

CREATE INDEX IF NOT EXISTS idx_posts_crawled_at ON posts(crawled_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_etf ON posts(etf_code);
CREATE INDEX IF NOT EXISTS idx_posts_source ON posts(source);
"""


def init_db():
    import os
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with _conn() as c:
        c.executescript(SCHEMA)


@contextmanager
def _conn():
    conn = sqlite3.connect(config.DB_PATH, isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def insert_post(post: dict) -> bool:
    """Insert a single post. Returns True if newly inserted."""
    post.setdefault("crawled_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with _conn() as c:
        cur = c.execute(
            """INSERT OR IGNORE INTO posts
            (source, post_id, etf_code, etf_name, title, content,
             post_date, author, likes, dislikes, comments, crawled_at)
            VALUES (:source, :post_id, :etf_code, :etf_name, :title, :content,
                    :post_date, :author, :likes, :dislikes, :comments, :crawled_at)""",
            {
                "source": post["source"],
                "post_id": post["post_id"],
                "etf_code": post["etf_code"],
                "etf_name": post["etf_name"],
                "title": post.get("title", ""),
                "content": post.get("content", ""),
                "post_date": post.get("post_date", ""),
                "author": post.get("author", ""),
                "likes": post.get("likes", 0),
                "dislikes": post.get("dislikes", 0),
                "comments": post.get("comments", 0),
                "crawled_at": post["crawled_at"],
            },
        )
        return cur.rowcount > 0


def existing_post_ids(source: str, etf_code: str) -> set[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT post_id FROM posts WHERE source=? AND etf_code=?",
            (source, etf_code),
        ).fetchall()
    return {r["post_id"] for r in rows}


def recent_posts(limit: int = 100, etf_code: str | None = None,
                 source: str | None = None) -> list[dict]:
    sql = "SELECT * FROM posts"
    conds, params = [], []
    if etf_code:
        conds.append("etf_code=?")
        params.append(etf_code)
    if source:
        conds.append("source=?")
        params.append(source)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY CASE WHEN post_date='' THEN crawled_at ELSE post_date END DESC, id DESC LIMIT ?"
    params.append(limit)
    with _conn() as c:
        rows = c.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) AS n FROM posts").fetchone()["n"]
        by_etf = c.execute(
            "SELECT etf_code, etf_name, source, COUNT(*) AS n "
            "FROM posts GROUP BY etf_code, source"
        ).fetchall()
        last_1h = c.execute(
            "SELECT COUNT(*) AS n FROM posts "
            "WHERE crawled_at >= datetime('now', 'localtime', '-1 hour')"
        ).fetchone()["n"]
    return {
        "total": total,
        "last_hour": last_1h,
        "by_etf_source": [dict(r) for r in by_etf],
    }
