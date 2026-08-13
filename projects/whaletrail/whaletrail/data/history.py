"""Build daily OHLCV history from accumulated tvscreener quote snapshots.

The tvscreener scanner serves current snapshots, not historical bars. This
module turns repeated snapshots (saved to ``quote_snapshots`` over time) into
a daily OHLCV series, which is the data path for low-frequency A-share paper
trading. One calendar day may have several snapshot rows:

- open  = first non-null open of the day
- high  = max high of the day
- low   = min low of the day
- close / volume = last non-null values of the day

Older rows predating the ``open/high/low`` columns fall back to ``close``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def build_daily_history(db_path: str | Path, tv_symbol: str) -> pd.DataFrame:
    """Aggregate ``quote_snapshots`` into one daily OHLCV bar per calendar date.

    Returns an empty DataFrame with the standard OHLCV columns when no
    snapshots exist for *tv_symbol*.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(
            "SELECT * FROM quote_snapshots WHERE tv_symbol = ? ORDER BY timestamp",
            conn,
            params=(tv_symbol,),
        )
    finally:
        conn.close()

    if df.empty:
        return pd.DataFrame(columns=_OHLCV_COLUMNS)

    # Timestamps are ISO8601 but mixed precision (some omit microseconds),
    # which breaks pandas' format inference. Keep only second precision.
    df["date"] = pd.to_datetime(df["timestamp"].astype(str).str[:19]).dt.normalize()
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = None

    def _first_non_null(series: pd.Series) -> float:
        values = series.dropna()
        return float(values.iloc[0]) if not values.empty else float("nan")

    grouped = df.groupby("date")
    out = pd.DataFrame(
        {
            "open": grouped["open"].apply(_first_non_null),
            "high": grouped["high"].max(),
            "low": grouped["low"].min(),
            "close": grouped["close"].last(),
            "volume": grouped["volume"].last(),
        }
    )
    out.index = pd.to_datetime(out.index)
    out.index.name = "date"
    out = out.sort_index()

    # Older snapshots only stored close; fill the other columns from it.
    for col in ("open", "high", "low"):
        out[col] = out[col].fillna(out["close"])
    out["volume"] = out["volume"].fillna(0).astype("int64")
    return out[_OHLCV_COLUMNS]
