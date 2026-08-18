"""Intraday OHLCV via yfinance, with Parquet accumulation.

yfinance caps intraday history (5m ≈ last 60 days, 1h ≈ 730 days).  Each
backtest fetch is merged into a local Parquet cache keyed
``<symbol>_<interval>`` (e.g. ``GLD_5m.parquet``), so repeated runs
accumulate a history that outlives the API window.

``10m`` bars are not served by yfinance and are resampled from ``5m``.

Live scanning (``paper-live.py``) uses :func:`fetch_bars` directly — no
cache writes on the hot path.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from whaletrail.data.cache import ParquetCache
from whaletrail.data.symbols import parse_symbol
from whaletrail.data.yfinance_source import YFinanceSource

logger = logging.getLogger(__name__)

_YF_COLUMN_MAP = {"Open": "open", "High": "high", "Low": "low",
                  "Close": "close", "Volume": "volume"}

# yfinance intraday history limits (calendar days back from today).
YF_LIMIT_DAYS = {"1m": 7, "5m": 60, "15m": 60, "30m": 60, "1h": 730}
# Intervals synthesised from a finer yfinance interval.
RESAMPLE_FROM = {"10m": "5m"}

ET = "America/New_York"

_RESAMPLE_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def fetch_bars(symbol: str, interval: str, start: date, end: date) -> pd.DataFrame:
    """Download intraday bars from yfinance (no cache interaction).

    Returns a tz-naive DataFrame indexed by ET wall-clock bar open times,
    columns ``open/high/low/close/volume``; empty on failure.
    """
    ticker = parse_symbol(symbol).ticker
    fetch_interval = RESAMPLE_FROM.get(interval, interval)
    if fetch_interval not in YF_LIMIT_DAYS:
        raise ValueError(
            f"unsupported interval {interval!r}; "
            f"known: {sorted(set(YF_LIMIT_DAYS) | set(RESAMPLE_FROM))}"
        )
    auto_adjust = ticker not in YFinanceSource._RAW_SYMBOLS
    logger.info("yfinance intraday fetch %s %s %s→%s", ticker, fetch_interval, start, end)
    try:
        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=end.isoformat(),
            interval=fetch_interval,
            auto_adjust=auto_adjust,
            progress=False,
        )
    except Exception:
        logger.exception("yfinance intraday failed %s %s", ticker, fetch_interval)
        return _empty_df()
    df = _normalize(df)
    if interval in RESAMPLE_FROM and not df.empty:
        df = _resample(df, interval)
    return df


def get_bars(
    symbol: str,
    interval: str,
    start: date,
    end: date,
    cache_dir: str | None = None,
) -> pd.DataFrame:
    """Intraday bars for [start, end], fetching fresh data and merging it
    into the accumulating Parquet cache.

    The requested range is clamped to the yfinance window for the interval;
    older rows can still come from the cache (previous runs' fetches).
    """
    ticker = parse_symbol(symbol).ticker
    fetch_interval = RESAMPLE_FROM.get(interval, interval)
    limit = YF_LIMIT_DAYS.get(fetch_interval)
    if limit is None:
        raise ValueError(f"unsupported interval {interval!r}")

    cache = ParquetCache(cache_dir)
    key = f"{ticker}_{interval}"

    earliest = date.today() - pd.Timedelta(days=limit).to_pytimedelta()
    fetch_start = max(start, earliest)
    if fetch_start <= end:
        fresh = fetch_bars(ticker, interval, fetch_start, end)
        if not fresh.empty:
            cache.put(key, fresh)
    else:
        logger.info(
            "requested range fully outside yfinance %s window (%d d); cache only",
            fetch_interval, limit,
        )

    cached = cache.get(key, start, end)
    return cached if cached is not None else _empty_df()


def _normalize(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return _empty_df()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    rename = {k: v for k, v in _YF_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename)
    df = df[[c for c in _YF_COLUMN_MAP.values() if c in df.columns]]
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(ET).tz_localize(None)
    df.index.name = "date"
    df = df.sort_index()
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0).astype("int64")
    return df


def _resample(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    minutes = int(interval[:-1])
    out = (
        df.resample(f"{minutes}min")
        .agg({k: v for k, v in _RESAMPLE_AGG.items() if k in df.columns})
        .dropna(subset=["close"])
    )
    if "volume" in out.columns:
        out["volume"] = out["volume"].fillna(0).astype("int64")
    out.index.name = "date"
    return out


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
