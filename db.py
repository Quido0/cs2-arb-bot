"""
SQLite storage for arbitrage opportunity history.
Table: opportunities — every found deal with timestamp.
"""
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "history.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                buy_price   REAL    NOT NULL,
                sell_price  REAL    NOT NULL,
                net_profit  REAL    NOT NULL,
                profit_pct  REAL    NOT NULL,
                qty         INTEGER NOT NULL,
                float_value REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ts   ON opportunities(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON opportunities(name)")
        conn.commit()


def save_opportunities(opps) -> None:
    """Save a list of Opportunity objects to the database."""
    if not opps:
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (
            ts,
            o.name,
            o.buy_price,
            o.sell_price,
            o.net_profit,
            o.profit_pct,
            o.qty,
            getattr(o, "float_value", None),
        )
        for o in opps
    ]
    with _connect() as conn:
        conn.executemany(
            "INSERT INTO opportunities "
            "(ts, name, buy_price, sell_price, net_profit, profit_pct, qty, float_value) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


def get_recent(limit: int = 200) -> List[Dict[str, Any]]:
    """Return the last N records, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM opportunities ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_summary() -> Dict[str, Any]:
    """Aggregated statistics across all history."""
    with _connect() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                   AS total,
                ROUND(SUM(net_profit), 2)  AS total_profit,
                ROUND(AVG(profit_pct), 1)  AS avg_pct,
                ROUND(MAX(profit_pct), 1)  AS best_pct,
                COUNT(DISTINCT name)        AS unique_items,
                MIN(ts)                     AS first_seen,
                MAX(ts)                     AS last_seen
            FROM opportunities
        """).fetchone()
    return dict(row) if row else {}


def get_top_items(limit: int = 10) -> List[Dict[str, Any]]:
    """Top items by total profit across all time."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT
                name,
                COUNT(*)                   AS appearances,
                ROUND(SUM(net_profit), 2)  AS total_profit,
                ROUND(AVG(profit_pct), 1)  AS avg_pct,
                ROUND(AVG(buy_price), 2)   AS avg_buy
            FROM opportunities
            GROUP BY name
            ORDER BY total_profit DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


# Initialise on import
init()
