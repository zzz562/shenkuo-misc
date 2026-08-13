#!/usr/bin/env python3
"""WhaleTrail backtest runner — gold-first, US hedge symbols via yfinance.

Usage:
  run-backtest.py [strategy] [symbol] [start] [end] [cash]

Defaults: gold_sma GLD 2018-01-01 2026-08-12 100000
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from whaletrail.data.layer import DataLayer
from whaletrail.data.symbols import parse_symbol
from whaletrail.engine.backtester import Backtester
from whaletrail.metrics.performance import calculate_metrics, compute_trade_pnl
from whaletrail.storage.repository import Repository
from whaletrail.strategy.registry import get_strategy_class

# Proxy config: WT_PROXY_URL → HTTPS_PROXY → default (Mac mini Clash).
# See docs/ENVIRONMENT.md "配置项（环境变量）".
PROXY = os.environ.get("WT_PROXY_URL") or os.environ.get("HTTPS_PROXY") or "http://127.0.0.1:7890"
os.environ.setdefault("HTTPS_PROXY", PROXY)
os.environ.setdefault("HTTP_PROXY", PROXY)

def main() -> None:
    strategy_name = sys.argv[1] if len(sys.argv) > 1 else "gold_sma"
    symbol = sys.argv[2] if len(sys.argv) > 2 else "GLD"
    start_str = sys.argv[3] if len(sys.argv) > 3 else "2018-01-01"
    end_str = sys.argv[4] if len(sys.argv) > 4 else "2026-08-12"
    cash = float(sys.argv[5]) if len(sys.argv) > 5 else 100_000.0

    # Validate scope (raises on A-share / HK)
    parsed = parse_symbol(symbol)
    ticker = parsed.ticker

    try:
        StrategyClass = get_strategy_class(strategy_name)
    except KeyError:
        from whaletrail.strategy.registry import list_strategies
        print(
            json.dumps(
                {"error": f"unknown strategy {strategy_name}", "known": list_strategies()},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    strategy = StrategyClass()
    src = DataLayer()

    bt = Backtester(
        symbols=[ticker],
        strategy=strategy,
        data_source=src,
        start=date.fromisoformat(start_str),
        end=date.fromisoformat(end_str),
        initial_cash=cash,
    )

    results = bt.run()

    # Enrich trades with realised P&L (FIFO) and compute the metric suite.
    results["trades"] = compute_trade_pnl(results.get("trades", []))
    results["metrics"] = calculate_metrics(
        results["trades"],
        [p["equity"] for p in results.get("equity_curve", [])],
        cash,
    )

    results["strategy"] = strategy_name
    results["symbol"] = ticker
    results["role"] = parsed.role
    results["market"] = parsed.market.value
    results["start"] = start_str
    results["end"] = end_str

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    timestamp = date.today().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"backtest_{strategy_name}_{ticker}_{timestamp}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, default=str, indent=2, ensure_ascii=False)

    # Persist run / trades / snapshots to SQLite for cross-run queries.
    try:
        repo = Repository(ROOT / "results" / "whaletrail.db")
        run_id = repo.save_run(
            strategy_name,
            [ticker],
            start_str,
            end_str,
            cash,
            results["final_equity"],
            results["metrics"],
        )
        for t in results["trades"]:
            repo.save_trade(
                run_id,
                {
                    "symbol": t.get("symbol", ""),
                    "side": str(t.get("side", "")).lower(),
                    "quantity": t.get("quantity", 0.0),
                    "price": t.get("price", 0.0),
                    "commission": t.get("commission", 0.0),
                    "timestamp": t.get("date", ""),
                    "pnl": t.get("pnl"),
                },
            )
        for p in results["equity_curve"]:
            repo.save_snapshot(run_id, p["date"], p["equity"], p["cash"], {})
        repo.close()
    except Exception as e:  # persistence must never fail the backtest
        print(f"  ⚠️ 持久化到 SQLite 失败: {e}", file=sys.stderr)

    summary = {
        "file": str(out_file),
        "strategy": strategy_name,
        "symbol": ticker,
        "role": parsed.role,
        "final_equity": round(results["final_equity"], 2),
        "total_return_pct": round(results["total_return"] * 100, 2),
        "trades": len(results["trades"]),
        "commission": round(results["total_commission"], 2),
        "sharpe": results["metrics"].get("sharpe_ratio"),
        "max_drawdown_pct": results["metrics"].get("max_drawdown"),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
