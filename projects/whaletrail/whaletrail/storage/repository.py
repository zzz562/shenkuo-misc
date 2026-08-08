"""Repository — high-level CRUD wrapper around the SQLite database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from whaletrail.storage.schema import create_tables


class Repository:
    """Persist and query backtest results.

    Parameters
    ----------
    db_path : str or Path
        Path to the SQLite database.  Created automatically if it does not
        exist.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = create_tables(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def save_run(
        self,
        strategy_name: str,
        symbols: list[str],
        start: str,
        end: str,
        initial_cash: float,
        final_equity: float,
        metrics: dict[str, Any],
    ) -> int:
        """Persist a completed backtest run and return its auto-generated ID."""
        cur = self.conn.execute(
            """INSERT INTO runs
               (strategy_name, symbols, start_date, end_date,
                initial_cash, final_equity, metrics_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                strategy_name,
                json.dumps(symbols, ensure_ascii=False),
                str(start),
                str(end),
                initial_cash,
                final_equity,
                json.dumps(metrics, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def save_trade(self, run_id: int, trade: dict[str, Any]) -> int:
        """Persist a single executed trade."""
        cur = self.conn.execute(
            """INSERT INTO trades
               (run_id, symbol, side, quantity, price, commission, timestamp, pnl)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                trade.get("symbol", ""),
                trade.get("side", ""),
                trade.get("quantity", 0.0),
                trade.get("price", 0.0),
                trade.get("commission", 0.0),
                str(trade.get("timestamp", "")),
                trade.get("pnl"),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def save_snapshot(
        self,
        run_id: int,
        date: str,
        equity: float,
        cash: float,
        positions: dict[str, Any],
    ) -> int:
        """Persist a daily portfolio snapshot."""
        cur = self.conn.execute(
            """INSERT INTO portfolio_snapshots
               (run_id, date, equity, cash, positions_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                run_id,
                str(date),
                equity,
                cash,
                json.dumps(positions, ensure_ascii=False),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_run(self, run_id: int) -> Optional[dict[str, Any]]:
        """Return a single run record as a dict, or *None*."""
        row = self.conn.execute(
            "SELECT * FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, "runs")

    def list_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent runs, newest first."""
        rows = self.conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(r, "runs") for r in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row, table: str) -> dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict with JSON fields decoded."""
        d = dict(row)
        if table == "runs":
            d["symbols"] = json.loads(d.get("symbols", "[]") or "[]")
            metrics_raw = d.get("metrics_json")
            d["metrics"] = json.loads(metrics_raw) if metrics_raw else {}
            d.pop("metrics_json", None)
        return d
