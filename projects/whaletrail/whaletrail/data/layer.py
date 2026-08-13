"""Unified market-data layer.

Combines the two data sources by role, not by naive fallback:

- Historical daily bars → :class:`YFinanceSource` (primary) + Parquet cache.
  tvscreener does not serve history; never use it for backfills.
- Current snapshots / watchlist → :class:`TVScreenerSource` (primary).
  yfinance remains the source for paper-live intraday bars.

See ``docs/ARCHITECTURE.md`` → "数据层组合".
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

import pandas as pd

from whaletrail.data.tvscreener_source import QuoteSnapshot, TVScreenerSource
from whaletrail.data.yfinance_source import YFinanceSource


class DataLayer:
    """Single entry point for market data access."""

    def __init__(
        self,
        yfinance: YFinanceSource | None = None,
        tvscreener: TVScreenerSource | None = None,
    ) -> None:
        self.yfinance = yfinance or YFinanceSource()
        self.tvscreener = tvscreener or TVScreenerSource()

    def get_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Historical daily OHLCV (yfinance + Parquet cache)."""
        return self.yfinance.get_daily(symbol, start, end)

    def get_quotes(self, symbols: Iterable[str]) -> list[QuoteSnapshot]:
        """Current scanner snapshots (tvscreener)."""
        return self.tvscreener.get_quotes(symbols)
