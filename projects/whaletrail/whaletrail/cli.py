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


def _import_backtester():
    engine = _import_engine()
    try:
        return engine.Backtester
    except AttributeError:
        raise click.ClickException(
            "Backtester class not found in whaletrail.engine.  "
            "Make sure engine/backtester.py defines a Backtester class."
        )


# ---------------------------------------------------------------------------
# Strategy registry (auto-discover, no hard-coded list after Phase 3)
# ---------------------------------------------------------------------------

_STRATEGY_MODULES: dict[str, str] = {
    "gold_sma": "whaletrail.strategy.strategies.gold_sma",
    "ma_cross": "whaletrail.strategy.strategies.ma_cross",
}


def _get_strategy_class(name: str):
    """Return the Strategy *class* for the given strategy name."""
    module_path = _STRATEGY_MODULES.get(name)
    if module_path is None:
        available = ", ".join(sorted(_STRATEGY_MODULES))
        raise click.ClickException(
            f"Unknown strategy '{name}'. Available: {available}"
        )

    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise click.ClickException(
            f"Failed to import strategy module '{module_path}': {exc}"
        )

    # Convention: the strategy class is the CamelCase version of the module name
    # plus "Strategy" suffix, or the last component.
    # We walk the module looking for a Strategy subclass to be safe.
    import inspect

    from whaletrail.strategy.base import Strategy

    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, Strategy) and obj is not Strategy:
            return obj

    raise click.ClickException(
        f"No Strategy subclass found in module '{module_path}'."
    )


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version="0.1.0", prog_name="whaletrail")
def main() -> None:
    """🐋 WhaleTrail — multi-market paper trading & backtesting system."""


# ---------------------------------------------------------------------------
# data fetch
# ---------------------------------------------------------------------------


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


@main.group()
def backtest() -> None:
    """Run backtests and view reports."""


@backtest.command("run")
@click.option(
    "--strategy", "-s", "strategy_name", required=True,
    help="Strategy name (e.g. ma_cross, gold_sma).",
)
@click.option(
    "--symbols", required=True,
    help="Comma-separated symbols (e.g. GLD,SPY).",
)
@click.option("--start", required=True, help="Start date (YYYY-MM-DD).")
@click.option("--end", required=True, help="End date (YYYY-MM-DD).")
@click.option("--cash", type=float, default=1_000_000.0, show_default=True,
              help="Initial cash.")
@click.option(
    "--output", "-o", "output_dir", default="results", show_default=True,
    help="Directory for output files (CSV, PNG).",
)
@click.option(
    "--db", "db_path", default="whaletrail.db", show_default=True,
    help="SQLite database path for persisting results.",
)
def backtest_run(
    strategy_name: str,
    symbols: str,
    start: str,
    end: str,
    cash: float,
    output_dir: str,
    db_path: str,
) -> None:
    """Run a backtest and persist results."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise click.ClickException("At least one symbol is required.")

    StrategyCls = _get_strategy_class(strategy_name)
    Backtester = _import_backtester()

    click.echo(f"🚀  WhaleTrail Backtest")
    click.echo(f"    Strategy : {strategy_name}")
    click.echo(f"    Symbols  : {', '.join(symbol_list)}")
    click.echo(f"    Period   : {start} → {end}")
    click.echo(f"    Cash     : {cash:,.0f}")
    click.echo()

    # Instantiate strategy.
    strategy = StrategyCls()

    # Build and run backtester.
    bt = Backtester(
        strategy=strategy,
        symbols=symbol_list,
        start_date=start,
        end_date=end,
        initial_cash=cash,
    )

    try:
        result = bt.run()
    except Exception as exc:
        raise click.ClickException(f"Backtest failed: {exc}")

    # ── Persist ──────────────────────────────────────────────────────────
    from whaletrail.storage.repository import Repository
    from whaletrail.metrics.performance import calculate_metrics

    repo = Repository(db_path)

    trades = result.get("trades", [])
    equity_curve = result.get("equity_curve", [])
    final_equity = equity_curve[-1] if equity_curve else cash

    metrics = calculate_metrics(trades, equity_curve, cash)

    run_id = repo.save_run(
        strategy_name=strategy_name,
        symbols=symbol_list,
        start=start,
        end=end,
        initial_cash=cash,
        final_equity=final_equity,
        metrics=metrics,
    )

    for trade in trades:
        repo.save_trade(run_id, trade)

    if "snapshots" in result:
        for snap in result["snapshots"]:
            repo.save_snapshot(
                run_id=run_id,
                date=str(snap.get("date", "")),
                equity=snap.get("equity", 0.0),
                cash=snap.get("cash", 0.0),
                positions=snap.get("positions", {}),
            )

    repo.close()

    # ── Output ───────────────────────────────────────────────────────────
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save equity curve CSV.
    import pandas as pd

    eq_df = pd.DataFrame({"equity": equity_curve})
    eq_csv = out_dir / f"equity_{run_id}.csv"
    eq_df.to_csv(eq_csv, index=False)

    # Save trades CSV.
    if trades:
        trades_df = pd.DataFrame(trades)
        trades_csv = out_dir / f"trades_{run_id}.csv"
        trades_df.to_csv(trades_csv, index=False)

    # ── Summary table ────────────────────────────────────────────────────
    try:
        from tabulate import tabulate
    except ImportError:
        tabulate = None  # fallback below

    summary_rows = [
        ("Run ID", run_id),
        ("Strategy", strategy_name),
        ("Symbols", ", ".join(symbol_list)),
        ("Period", f"{start} → {end}"),
        ("Initial Cash", f"{cash:,.2f}"),
        ("Final Equity", f"{final_equity:,.2f}"),
        ("Total Return", f"{metrics['total_return']:.2f} %"),
        ("Annual Return", f"{metrics['annual_return']:.2f} %"),
        ("Sharpe Ratio", f"{metrics['sharpe_ratio']:.4f}"),
        ("Max Drawdown", f"{metrics['max_drawdown']:.2f} %"),
        ("Win Rate", f"{metrics['win_rate']:.2%}"),
        ("Profit Factor", f"{metrics['profit_factor']}"),
        ("Total Trades", metrics["total_trades"]),
    ]

    click.echo()
    if tabulate:
        click.echo(tabulate(summary_rows, headers=["Metric", "Value"],
                            tablefmt="simple", colalign=("right", "left")))
    else:
        for k, v in summary_rows:
            click.echo(f"  {k:>15s} : {v}")

    click.echo()
    click.echo(f"📁  Results saved to {out_dir.resolve()}")
    click.echo(f"💾  Run persisted as ID {run_id} in {db_path}")


@backtest.command("report")
@click.option("--run-id", type=int, required=True, help="Run ID to report.")
@click.option(
    "--db", "db_path", default="whaletrail.db", show_default=True,
    help="SQLite database path.",
)
def backtest_report(run_id: int, db_path: str) -> None:
    """Display a detailed report for a previous backtest run."""
    from whaletrail.storage.repository import Repository

    repo = Repository(db_path)
    run = repo.get_run(run_id)
    repo.close()

    if run is None:
        raise click.ClickException(f"No run found with ID {run_id}.")

    try:
        from tabulate import tabulate
    except ImportError:
        tabulate = None

    click.echo(f"\n📊  Backtest Report — Run #{run_id}\n")

    # Header.
    meta_rows = [
        ("Strategy", run["strategy_name"]),
        ("Symbols", ", ".join(run["symbols"])),
        ("Period", f"{run['start_date']} → {run['end_date']}"),
        ("Initial Cash", f"{run['initial_cash']:,.2f}"),
        ("Final Equity", f"{run.get('final_equity', 'N/A')}"),
    ]
    if tabulate:
        click.echo(tabulate(meta_rows, headers=["Field", "Value"],
                            tablefmt="simple", colalign=("right", "left")))
    else:
        for k, v in meta_rows:
            click.echo(f"  {k:>15s} : {v}")

    # Metrics.
    metrics = run.get("metrics", {})
    if metrics:
        click.echo("\n📈  Performance Metrics\n")
        metric_rows = [
            ("Total Return", f"{metrics.get('total_return', 0):.2f} %"),
            ("Annual Return", f"{metrics.get('annual_return', 0):.2f} %"),
            ("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.4f}"),
            ("Max Drawdown", f"{metrics.get('max_drawdown', 0):.2f} %"),
            ("Volatility", f"{metrics.get('volatility', 0):.2f} %"),
            ("Win Rate", f"{metrics.get('win_rate', 0):.2%}"),
            ("Profit Factor", f"{metrics.get('profit_factor', 0)}"),
            ("Total Trades", metrics.get("total_trades", 0)),
        ]
        if tabulate:
            click.echo(
                tabulate(metric_rows, headers=["Metric", "Value"],
                         tablefmt="simple", colalign=("right", "left"))
            )
        else:
            for k, v in metric_rows:
                click.echo(f"  {k:>15s} : {v}")

    click.echo()


# ---------------------------------------------------------------------------
# strategy
# ---------------------------------------------------------------------------


@main.group()
def strategy() -> None:
    """Explore available trading strategies."""


@strategy.command("list")
def strategy_list() -> None:
    """List all available strategies."""
    click.echo("\n📋  Available Strategies\n")
    for name in sorted(_STRATEGY_MODULES):
        try:
            cls = _get_strategy_class(name)
            doc = (cls.__doc__ or "").strip().split("\n")[0]
            click.echo(f"  {name:20s}  {doc}")
        except Exception:
            click.echo(f"  {name:20s}  (import failed)")

    click.echo()


@strategy.command("info")
@click.option("--name", "-n", required=True, help="Strategy name.")
def strategy_info(name: str) -> None:
    """Display details about a specific strategy."""
    cls = _get_strategy_class(name)

    click.echo(f"\n🧠  Strategy: {name}\n")

    # Docstring.
    doc = (cls.__doc__ or "No description available.").strip()
    click.echo(doc)
    click.echo()

    # Attributes.
    import inspect

    sig = inspect.signature(cls.__init__)  # type: ignore[misc]
    params = list(sig.parameters.values())[1:]  # skip 'self'
    if params:
        click.echo("Parameters")
        click.echo("----------")
        for p in params:
            default = p.default if p.default is not inspect.Parameter.empty else ""
            click.echo(f"  {p.name:20s}  (default: {default!r})")
        click.echo()

    # Module source location.
    try:
        source_file = inspect.getfile(cls)
        click.echo(f"Source: {source_file}")
    except Exception:
        pass

    click.echo()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
