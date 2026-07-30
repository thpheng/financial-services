"""SQLite log of every completed/aborted round trip, independent of moomoo's
own order history -- gives you a running P&L record for the strategy."""
import sqlite3
import time
from contextlib import closing

SCHEMA = """
CREATE TABLE IF NOT EXISTS round_trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    closed_at REAL NOT NULL,
    code TEXT NOT NULL,
    qty REAL NOT NULL,
    buy_price REAL NOT NULL,
    sell_price REAL,
    captured_edge REAL,
    forced_exit INTEGER NOT NULL DEFAULT 0,
    aborted INTEGER NOT NULL DEFAULT 0,
    note TEXT
);
"""

CONTRACT_MULTIPLIER = 100  # standard US equity option multiplier


def init_db(path: str) -> None:
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def log_round_trip(path: str, rt) -> int:
    captured_edge = None
    if rt.sell_price is not None:
        captured_edge = (rt.sell_price - rt.buy_price) * rt.qty * CONTRACT_MULTIPLIER
    with closing(sqlite3.connect(path)) as conn:
        cur = conn.execute(
            """INSERT INTO round_trips
               (closed_at, code, qty, buy_price, sell_price, captured_edge,
                forced_exit, aborted, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                time.time(), getattr(rt, "code", ""), rt.qty, rt.buy_price, rt.sell_price,
                captured_edge, int(rt.forced_exit), int(rt.aborted), rt.note,
            ),
        )
        conn.commit()
        return cur.lastrowid


def summary(path: str) -> dict:
    with closing(sqlite3.connect(path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(captured_edge), 0), "
            "COALESCE(SUM(forced_exit), 0) FROM round_trips"
        ).fetchone()
        return {"round_trips": row[0], "total_captured_edge": row[1], "forced_exits": row[2]}


def recent(path: str, limit: int = 50) -> list:
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM round_trips ORDER BY closed_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
