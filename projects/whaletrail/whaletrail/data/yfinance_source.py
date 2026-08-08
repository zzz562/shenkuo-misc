"""Yahoo Finance + Parquet cache — gold / US daily data."""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from whaletrail.data.base import DataSource
from whaletrail.data.cache import ParquetCache
from whaletrail.data.symbols import parse_symbol

logger = logging.getLogger(__name__)

_YF_COLUMN_MAP = {"Open": "open", "High": "high", "Low": "low",
                  "Close": "close", "Volume": "volume"}


class YFinanceSource(DataSource):
    """Daily OHLCV, cached in Parquet. Cache-hit → instant. Cache-miss → fetch + save."""

    _RAW_SYMBOLS = frozenset({"GC=F", "SI=F", "HG=F"})

    def __init__(self, cache_dir: str | None = None):
        self._cache = ParquetCache(cache_dir)

    def get_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        parsed = parse_symbol(symbol)
        ticker = parsed.ticker

        # 1) Hit cache
        cached = self._cache.get(ticker, start, end)
        if cached is not None and len(cached) > 0:
            logger.debug("cache hit %s (%d rows)", ticker, len(cached))
            return cached

        # 2) Fetch
        auto_adjust = ticker not in self._RAW_SYMBOLS
        logger.info("yfinance fetch %s %s→%s", ticker, start.isoformat(), end.isoformat())

        try:
            df = yf.download(ticker, start=start.isoformat(), end=end.isoformat(),
                             auto_adjust=auto_adjust, progress=False)
        except Exception:
            logger.exception("yfinance failed %s", ticker)
            return _empty_df()
        if df is None or df.empty:
            return _empty_df()

        # Normalise
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        rename = {k: v for k, v in _YF_COLUMN_MAP.items() if k in df.columns}
        df = df.rename(columns=rename)
        df = df[[c for c in _YF_COLUMN_MAP.values() if c in df.columns]]
        if isinstance(df.index, pd.MultiIndex):
            df.index = df.index.get_level_values("Date")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df = df.sort_index()
        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0).astype("int64")

        # 3) Cache
        self._cache.put(ticker, df)
        return df


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
