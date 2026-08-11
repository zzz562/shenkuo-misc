"""Data layer — yfinance + TradingView screener + Parquet cache (gold / US only)."""

from whaletrail.data.base import DataSource
from whaletrail.data.cache import ParquetCache
from whaletrail.data.symbols import Market, Symbol, is_gold_focus, parse_symbol
from whaletrail.data.tvscreener_source import (
    QuoteSnapshot,
    TVScreenerSource,
    snapshots_to_frame,
)
from whaletrail.data.watchlist import (
    WatchlistItem,
    by_tv_symbol,
    by_yahoo_symbol,
    load_watchlist,
    tv_symbols,
)
from whaletrail.data.yfinance_source import YFinanceSource

__all__ = [
    "DataSource",
    "Market",
    "ParquetCache",
    "QuoteSnapshot",
    "Symbol",
    "TVScreenerSource",
    "WatchlistItem",
    "YFinanceSource",
    "by_tv_symbol",
    "by_yahoo_symbol",
    "is_gold_focus",
    "load_watchlist",
    "parse_symbol",
    "snapshots_to_frame",
    "tv_symbols",
]
