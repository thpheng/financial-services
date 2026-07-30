"""SQLite audit log of every webhook received, independent of moomoo/OpenD
so the history survives even when the gateway is unreachable."""
import hashlib
import sqlite3
import time
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS webhook_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at REAL NOT NULL,
    payload_hash TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    symbol TEXT,
    side TEXT,
    qty INTEGER,
    order_type TEXT,
    price REAL,
    status TEXT NOT NULL,
    order_id TEXT,
    order_status TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_webhook_log_hash_time ON webhook_log (payload_hash, received_at);
"""

DEDUPE_WINDOW_SECONDS = 60


def init_db(path: str) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def payload_hash(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def is_duplicate(path: str, phash: str) -> bool:
    cutoff = time.time() - DEDUPE_WINDOW_SECONDS
    with closing(sqlite3.connect(path)) as conn:
        row = conn.execute(
            "SELECT 1 FROM webhook_log WHERE payload_hash = ? AND received_at > ? LIMIT 1",
            (phash, cutoff),
        ).fetchone()
        return row is not None


def log_event(path: str, *, raw_body: bytes, symbol=None, side=None, qty=None,
              order_type=None, price=None, status: str, order_id=None,
              order_status=None, error=None) -> int:
    with closing(sqlite3.connect(path)) as conn:
        cur = conn.execute(
            """INSERT INTO webhook_log
               (received_at, payload_hash, raw_payload, symbol, side, qty,
                order_type, price, status, order_id, order_status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(),
                payload_hash(raw_body),
                raw_body.decode("utf-8", errors="replace"),
                symbol, side, qty, order_type, price, status, order_id, order_status, error,
            ),
        )
        conn.commit()
        return cur.lastrowid


def recent_events(path: str, limit: int = 50) -> list:
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM webhook_log ORDER BY received_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
