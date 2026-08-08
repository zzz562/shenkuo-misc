"""SQLite schema for the WhaleTrail paper trading system.

Tables
------
- ``runs``          — one row per backtest run; stores parameters and summary metrics.
- ``trades``        — every fill (executed trade) during a run.
- ``portfolio_snapshots`` — daily equity/cash/positions snapshots.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT    NOT NULL,
    symbols         TEXT    NOT NULL,  -- JSON array of symbol strings
    start_date      TEXT    NOT NULL,  -- YYYY-MM-DD
    end_date        TEXT    NOT NULL,  -- YYYY-MM-DD
    initial_cash    REAL    NOT NULL,
    final_equity    REAL,
    metrics_json    TEXT,              -- JSON blob with all performance metrics
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    symbol          TEXT    NOT NULL,
    side            TEXT    NOT NULL CHECK(side IN ('buy', 'sell')),
    quantity        REAL    NOT NULL,
    price           REAL    NOT NULL,
    commission      REAL    NOT NULL DEFAULT 0.0,
    timestamp       TEXT    NOT NULL,  -- ISO-8601 or YYYY-MM-DD
    pnl             REAL              -- realised P&L for closing trades
);

CREATE INDEX IF NOT EXISTS idx_trades_run_id ON trades(run_id);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    date            TEXT    NOT NULL,  -- YYYY-MM-DD
    equity          REAL    NOT NULL,
    cash            REAL    NOT NULL,
    positions_json  TEXT    NOT NULL   -- JSON blob: {symbol: {qty, avg_cost, market_value}}
);

CREATE INDEX IF NOT EXISTS idx_snapshots_run_id ON portfolio_snapshots(run_id);
"""


def create_tables(db_path: str | Path) -> sqlite3.Connection:
    """Create (or upgrade) all tables in the SQLite database at *db_path*.

    Parameters
    ----------
    db_path : str or Path
        Filesystem path to the SQLite database file.

    Returns
    -------
    sqlite3.Connection
        An open connection to the database.  The caller is responsible for
        closing it when done.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
