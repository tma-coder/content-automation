import sqlite3
import hashlib
from datetime import datetime
from typing import Optional
import config


def _connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_hash TEXT UNIQUE NOT NULL,
            source_url TEXT NOT NULL,
            source_title TEXT NOT NULL,
            generated_title TEXT,
            short_text TEXT,
            long_text TEXT,
            hashtags TEXT,
            image_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS post_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            post_id TEXT,
            error_message TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.close()


def hash_url(url):
    return hashlib.sha256(url.encode()).hexdigest()


def article_exists(source_url):
    conn = _connect()
    row = conn.execute("SELECT 1 FROM articles WHERE source_hash = ?", (hash_url(source_url),)).fetchone()
    conn.close()
    return row is not None


def save_article(source_url, source_title, generated_title, short_text, long_text, hashtags, image_path, status="pending"):
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO articles (source_hash, source_url, source_title, generated_title, short_text, long_text, hashtags, image_path, status) VALUES (?,?,?,?,?,?,?,?,?)",
        (hash_url(source_url), source_url, source_title, generated_title, short_text, long_text, hashtags, image_path, status)
    )
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid


def get_article(article_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_articles():
    conn = _connect()
    rows = conn.execute("SELECT * FROM articles WHERE status = 'pending' ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_article_status(article_id, status):
    conn = _connect()
    posted = datetime.utcnow().isoformat() if status == "posted" else None
    conn.execute("UPDATE articles SET status = ?, posted_at = ? WHERE id = ?", (status, posted, article_id))
    conn.commit()
    conn.close()


def log_post(article_id, platform, success, post_id="", error_message=""):
    conn = _connect()
    conn.execute("INSERT INTO post_log (article_id, platform, success, post_id, error_message) VALUES (?,?,?,?,?)",
                 (article_id, platform, int(success), post_id, error_message))
    conn.commit()
    conn.close()


def get_post_history(limit=20):
    conn = _connect()
    rows = conn.execute("""
        SELECT a.id, a.generated_title, a.status, a.created_at,
               GROUP_CONCAT(p.platform || ':' || CASE WHEN p.success THEN 'ok' ELSE 'fail' END) as platforms
        FROM articles a LEFT JOIN post_log p ON a.id = p.article_id
        WHERE a.status IN ('posted', 'failed')
        GROUP BY a.id ORDER BY a.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_post_count(platform):
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM post_log WHERE platform = ? AND success = 1 AND DATE(posted_at) = DATE('now')",
        (platform,)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0
