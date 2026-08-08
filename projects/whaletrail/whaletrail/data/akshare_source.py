"""Akshare data source for China A-shares and Hong Kong stocks."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

try:
    import akshare as ak
except ImportError:  # pragma: no cover
    ak = None  # type: ignore[assignment]

from whaletrail.data.base import DataSource
from whaletrail.data.symbols import Market, parse_symbol

logger = logging.getLogger(__name__)

# Standard output columns
_STD_COLS = ["open", "high", "low", "close", "volume"]


class AkShareSource(DataSource):
    """Daily OHLCV data from Akshare.

    Covers China A-shares (Shanghai / Shenzhen) and Hong Kong stocks.
    """

    def __init__(self) -> None:
        if ak is None:
            raise ImportError(
                "akshare is required for AkShareSource. "
                "Install it with: pip install akshare"
            )

    def get_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Fetch daily bars from Akshare.

        Parameters
        ----------
        symbol : str
            Raw symbol (e.g. ``"600519.SH"``, ``"00700.HK"``).
        start : date
        end : date

        Returns
        -------
        pd.DataFrame
            Standardised OHLCV DataFrame.
        """
        parsed = parse_symbol(symbol)

        if parsed.market == Market.CN:
            return self._get_cn_daily(parsed.ticker, start, end)
        elif parsed.market == Market.HK:
            return self._get_hk_daily(parsed.ticker, start, end)
        else:
            raise ValueError(
                f"AkShareSource does not support market {parsed.market.value!r}. "
                f"Use YFinanceSource for {parsed.raw!r}."
            )

    # ------------------------------------------------------------------
    #  A-shares
    # ------------------------------------------------------------------

    _CN_COLUMN_MAP: dict[str, str] = {
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }

    def _get_cn_daily(
        self,
        code: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Fetch A-share daily data via ``ak.stock_zh_a_hist()``."""
        logger.info("akshare A-share download: code=%s  %s → %s", code, start, end)

        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",  # forward-adjusted
            )
        except Exception:
            logger.exception("akshare A-share download failed for %s", code)
            return _empty_df()

        return self._normalise_akshare(df, self._CN_COLUMN_MAP)

    # ------------------------------------------------------------------
    #  Hong Kong
    # ------------------------------------------------------------------

    _HK_COLUMN_MAP: dict[str, str] = {
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
    }

    def _get_hk_daily(
        self,
        code: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Fetch HK stock daily data via ``ak.stock_hk_hist()``."""
        logger.info("akshare HK download: code=%s  %s → %s", code, start, end)

        try:
            df = ak.stock_hk_hist(
                symbol=code,
                period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
        except Exception:
            logger.exception("akshare HK download failed for %s", code)
            return _empty_df()

        # Akshare `stock_hk_hist` sometimes returns columns in English
        # for HK data.  Detect and remap accordingly.
        if "open" in (c.lower() for c in df.columns):
            # Already in English – simple rename
            return self._normalise_akshare(
                df,
                {"开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"},
            )

        return self._normalise_akshare(df, self._HK_COLUMN_MAP)

    # ------------------------------------------------------------------
    #  Shared normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_akshare(
        df: pd.DataFrame,
        column_map: dict[str, str],
    ) -> pd.DataFrame:
        """Rename columns, set datetime index, ensure standard OHLCV output.

        Parameters
        ----------
        df : pd.DataFrame
            Raw akshare response.
        column_map : dict[str, str]
            Mapping from akshare column name → standard name.

        Returns
        -------
        pd.DataFrame
        """
        if df is None or df.empty:
            return _empty_df()

        # Rename columns that exist
        rename: dict[str, str] = {}
        for old, new in column_map.items():
            if old in df.columns:
                rename[old] = new

        df = df.rename(columns=rename)

        # --- Datetime index ---
        date_col = None
        for candidate in ("日期", "date", "Date", "trade_date"):
            if candidate in df.columns:
                date_col = candidate
                break

        if date_col is not None:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.dropna(subset=[date_col])
            df = df.set_index(date_col)
        else:
            # Fall back to current positional index as datetime
            logger.warning("No date column found in akshare response; using row index.")

        df.index = pd.to_datetime(df.index)
        df.index.name = "date"

        # Ensure tz-naive
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Keep only standard columns that are present
        present = [c for c in _STD_COLS if c in df.columns]
        df = df[present].copy()

        # Handle volume as integer, fill NAs with 0
        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0).astype("int64")

        df = df.sort_index()
        logger.debug("akshare normalised %d rows", len(df))
        return df


def _empty_df() -> pd.DataFrame:
    """Return an empty DataFrame with the standard OHLCV columns."""
    return pd.DataFrame(columns=_STD_COLS)
