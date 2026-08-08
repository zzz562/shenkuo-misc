"""Yahoo Finance data source via yfinance."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import yfinance as yf

from whaletrail.data.base import DataSource
from whaletrail.data.symbols import Market, parse_symbol

logger = logging.getLogger(__name__)

# Map yfinance column names → standard OHLCV
_YF_COLUMN_MAP: dict[str, str] = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


class YFinanceSource(DataSource):
    """Daily OHLCV data from Yahoo Finance.

    Covers US equities and COMEX gold futures (``GC=F``).
    """

    # Symbols for which yfinance’s auto_adjust behaviour may produce
    # unexpected column names – we disable it for those.
    _RAW_SYMBOLS = frozenset({"GC=F"})

    def get_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch daily bars via ``yfinance.download()``.

        Parameters
        ----------
        symbol : str
            Raw symbol (e.g. ``"AAPL"``, ``"GC=F"``).
        start : date
        end : date

        Returns
        -------
        pd.DataFrame
            Standardised OHLCV DataFrame.
        """
        parsed = parse_symbol(symbol)
        ticker = parsed.ticker

        # yfinance uses 'yyyy-mm-dd' strings
        start_str = start.isoformat()
        end_str = end.isoformat()

        auto_adjust = ticker not in self._RAW_SYMBOLS

        logger.info(
            "yfinance download: ticker=%s  %s → %s  auto_adjust=%s",
            ticker,
            start_str,
            end_str,
            auto_adjust,
        )

        try:
            df = yf.download(
                ticker,
                start=start_str,
                end=end_str,
                auto_adjust=auto_adjust,
                progress=False,
            )
        except Exception:
            logger.exception("yfinance download failed for %s", ticker)
            return _empty_df()

        if df is None or df.empty:
            logger.debug("yfinance returned empty DataFrame for %s", ticker)
            return _empty_df()

        # ── Normalise column names ─────────────────────────────────────
        # yfinance may return a MultiIndex columns when downloading a
        # single ticker; handle both cases gracefully.
        if isinstance(df.columns, pd.MultiIndex):
            # Drop the ticker level – keep Price columns only
            df.columns = df.columns.get_level_values(0)

        # Rename and keep only standard columns
        rename = {k: v for k, v in _YF_COLUMN_MAP.items() if k in df.columns}
        df = df.rename(columns=rename)
        df = df[[c for c in _YF_COLUMN_MAP.values() if c in df.columns]]

        # ── Flatten index ──────────────────────────────────────────────
        if isinstance(df.index, pd.MultiIndex):
            df.index = df.index.get_level_values("Date")
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"

        # Ensure tz-naive
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        df = df.sort_index()

        # ── Fill missing volume with 0 ─────────────────────────────────
        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0).astype("int64")

        logger.debug("yfinance returned %d rows for %s", len(df), ticker)
        return df


def _empty_df() -> pd.DataFrame:
    """Return an empty DataFrame with the standard OHLCV columns."""
    return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
