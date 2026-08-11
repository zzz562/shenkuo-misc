"""WhaleTrail CLI — paper trading & backtesting command-line interface.

Usage
-----
.. code-block:: bash

    python -m whaletrail.cli data fetch --symbol GLD --start 2020-01-01 --end 2024-12-31
    python -m whaletrail.cli backtest run --strategy gold_sma --symbols GLD --start 2018-01-01 --end 2024-12-31 --cash 100000
    python -m whaletrail.cli backtest report --run-id 1
    python -m whaletrail.cli strategy list
    python -m whaletrail.cli strategy info --name ma_cross
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import click

# ---------------------------------------------------------------------------
# Lazy imports for modules that may not be fully built yet.
# ---------------------------------------------------------------------------


def _import_data():
    """Import data module; raise with a helpful message if unavailable."""
    try:
        return importlib.import_module("whaletrail.data")
    except ImportError:
        raise click.ClickException(
            "The whaletrail.data module is not available.  "
            "Build it first (Phase 1 of the PLAN)."
        )


def _import_engine():
    try:
        return importlib.import_module("whaletrail.engine")
    except ImportError:
        raise click.ClickException(
            "The whaletrail.engine module is not available.  "
            "Build it first (Phase 2 of the PLAN)."
        )




# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version="0.1.0", prog_name="whaletrail")
def main() -> None:
    """WhaleTrail -- multi-market paper trading & backtesting system."""


@main.group()
def data() -> None:
    """Download and cache market data."""


@data.command("fetch")
@click.option("--symbol", "-s", required=True, help="Symbol to fetch (e.g. GLD, SPY, AAPL).")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD).")
@click.option("--end", required=True, help="End date (YYYY-MM-DD).")
@click.option(
    "--cache-dir",
    default="data/cache",
    show_default=True,
    help="Directory for local parquet cache.",
)
def data_fetch(symbol: str, start: str, end: str, cache_dir: str) -> None:
    """Fetch historical OHLCV data for SYMBOL and cache locally."""
    data_mod = _import_data()

    try:
        source = data_mod.get_source(symbol)  # type: ignore[attr-defined]
    except Exception as exc:
        raise click.ClickException(f"Failed to get data source for {symbol}: {exc}")

    click.echo(f"⬇  Fetching {symbol} from {start} to {end} …")

    try:
        df = source.get_daily(symbol, start, end)
    except Exception as exc:
        raise click.ClickException(f"Data fetch failed: {exc}")

    if df is None or df.empty:
        raise click.ClickException(f"No data returned for {symbol} in [{start}, {end}].")

    # Cache.
    cache_path = Path(cache_dir) / f"{symbol}.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path)

    click.echo(
        f"✅  Cached {len(df)} rows to {cache_path}  "
        f"[{df.index[0]} → {df.index[-1]}]"
    )


# ---------------------------------------------------------------------------
# backtest
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# backtest -- use scripts/run-backtest.py instead
# (CLI backtest is deprecated; the standalone script is the canonical entry point)
# ---------------------------------------------------------------------------


@main.group()
def backtest() -> None:
    """Run backtests (see scripts/run-backtest.py for full functionality)."""
    click.echo("Use scripts/run-backtest.py for backtesting. See docs/SCOPE.md.")


@main.command("strategies")
def list_strats() -> None:
    """List all registered strategies."""
    for name in list_strategies():
        click.echo(name)
