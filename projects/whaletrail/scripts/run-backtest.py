#!/usr/bin/env python3
"""WhaleTrail backtest runner — gold-first, US hedge symbols via yfinance.

Usage:
  run-backtest.py [strategy] [symbol] [start] [end] [cash]

Defaults: gold_sma GLD 2018-01-01 2024-12-31 100000
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from whaletrail.data.symbols import parse_symbol
from whaletrail.data.yfinance_source import YFinanceSource
from whaletrail.engine.backtester import Backtester
from whaletrail.strategy.strategies.bollinger import BollingerStrategy
from whaletrail.strategy.strategies.gold_sma import GoldSMAStrategy
from whaletrail.strategy.strategies.ma_cross import MACrossStrategy
from whaletrail.strategy.strategies.momentum import MomentumStrategy
from whaletrail.strategy.strategies.turtle import TurtleStrategy

# Default HTTPS proxy for Yahoo if not set (Mac mini Clash)
os.environ.setdefault("HTTPS_PROXY", os.environ.get("HTTPS_PROXY", "http://127.0.0.1:7890"))
os.environ.setdefault("HTTP_PROXY", os.environ.get("HTTP_PROXY", "http://127.0.0.1:7890"))

STRAT_MAP = {
    "gold_sma": GoldSMAStrategy,
    "ma_cross": MACrossStrategy,
    "bollinger": BollingerStrategy,
    "turtle": TurtleStrategy,
    "momentum": MomentumStrategy,
}


def main() -> None:
    strategy_name = sys.argv[1] if len(sys.argv) > 1 else "gold_sma"
    symbol = sys.argv[2] if len(sys.argv) > 2 else "GLD"
    start_str = sys.argv[3] if len(sys.argv) > 3 else "2018-01-01"
    end_str = sys.argv[4] if len(sys.argv) > 4 else "2024-12-31"
    cash = float(sys.argv[5]) if len(sys.argv) > 5 else 100_000.0

    # Validate scope (raises on A-share / HK)
    parsed = parse_symbol(symbol)
    ticker = parsed.ticker

    StrategyClass = STRAT_MAP.get(strategy_name)
    if StrategyClass is None:
        print(
            json.dumps(
                {"error": f"unknown strategy {strategy_name}", "known": list(STRAT_MAP)},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    strategy = StrategyClass()
    src = YFinanceSource()

    bt = Backtester(
        symbols=[ticker],
        strategy=strategy,
        data_source=src,
        start=date.fromisoformat(start_str),
        end=date.fromisoformat(end_str),
        initial_cash=cash,
    )

    results = bt.run()
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

    summary = {
        "file": str(out_file),
        "strategy": strategy_name,
        "symbol": ticker,
        "role": parsed.role,
        "final_equity": round(results["final_equity"], 2),
        "total_return_pct": round(results["total_return"] * 100, 2),
        "trades": len(results["trades"]),
        "commission": round(results["total_commission"], 2),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
