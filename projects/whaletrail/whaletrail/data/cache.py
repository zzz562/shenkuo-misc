"""Parquet-based local cache for daily OHLCV data."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)


class ParquetCache:
    """File-system cache storing DataFrames as Parquet files.

    Each symbol gets its own file: ``<symbol>.parquet`` inside
    *cache_dir*.  The cache is **append-only** — calling :meth:`put`
    merges new data with any existing rows (upsert by date).

    Parameters
    ----------
    cache_dir : str or Path, optional
        Directory for ``.parquet`` files.  Defaults to
        ``../data_cache`` relative to this module's directory.
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent.parent.parent / "data_cache"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    #  Public API
    # ------------------------------------------------------------------

    def get(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame | None:
        """Retrieve cached data for *symbol*, optionally sliced by date.

        Parameters
        ----------
        symbol : str
            Raw symbol string (used as the file name stem).
        start : date, optional
        end : date, optional

        Returns
        -------
        pd.DataFrame or None
            Cached OHLCV DataFrame, or ``None`` on cache miss.
        """
        path = self._path_for(symbol)
        if not path.exists():
            logger.debug("Cache miss: %s", path)
            return None

        try:
            df = pd.read_parquet(path)
        except Exception:
            logger.exception("Failed to read cache file %s", path)
            return None

        if df.empty:
            return None

        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Slice by date range
        if start is not None:
            df = df[df.index >= pd.Timestamp(start)]
        if end is not None:
            df = df[df.index <= pd.Timestamp(end)]

        logger.debug("Cache hit: %s  %d rows", symbol, len(df))
        return df if not df.empty else None

    def put(self, symbol: str, df: pd.DataFrame) -> None:
        """Write (or merge) *df* into the cache for *symbol*.

        Existing cached rows for the same dates are overwritten; rows
        for new dates are appended.

        Parameters
        ----------
        symbol : str
            Raw symbol string.
        df : pd.DataFrame
            OHLCV data — must have a ``DatetimeIndex``.
        """
        if df is None or df.empty:
            return

        path = self._path_for(symbol)

        # Merge with existing cache if present
        existing: pd.DataFrame | None = None
        if path.exists():
            try:
                existing = pd.read_parquet(path)
            except Exception:
                logger.warning("Could not read existing cache for %s; overwriting.", symbol)

        if existing is not None and not existing.empty:
            if not isinstance(existing.index, pd.DatetimeIndex):
                existing.index = pd.to_datetime(existing.index)
            if existing.index.tz is not None:
                existing.index = existing.index.tz_localize(None)

            # Combine: new rows take precedence on overlapping dates
            combined = pd.concat([existing, df])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
        else:
            combined = df.sort_index()

        try:
            combined.to_parquet(path, index=True)
            logger.info("Cached %d rows → %s", len(combined), path.name)
        except Exception:
            logger.exception("Failed to write cache file %s", path)

    def clear(self) -> None:
        """Remove all cache files from *cache_dir*."""
        if not self.cache_dir.exists():
            return

        count = 0
        for entry in self.cache_dir.iterdir():
            if entry.suffix == ".parquet":
                entry.unlink()
                count += 1

        logger.info("Cleared %d parquet files from %s", count, self.cache_dir)

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    def _path_for(self, symbol: str) -> Path:
        """Return the cache file path for *symbol*.

        Sanitises the symbol string so it can be used as a file name.
        """
        # Replace characters unsafe for file names
        safe = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self.cache_dir / f"{safe}.parquet"
