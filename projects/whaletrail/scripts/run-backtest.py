#!/usr/bin/env python3
"""WhaleTrail backtest runner — outputs JSON for OpenClaw consumption.

Usage: run-backtest.py <strategy> <symbol> [start] [end] [cash]
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from whaletrail.data.yfinance_source import YFinanceSource
from whaletrail.data.akshare_source import AkShareSource
from whaletrail.engine.backtester import Backtester
from whaletrail.strategy.strategies.gold_sma import GoldSMAStrategy
from whaletrail.strategy.strategies.ma_cross import MACrossStrategy
from whaletrail.data.symbols import parse_symbol

STRAT_MAP = {
    "gold_sma": GoldSMAStrategy,
    "ma_cross": MACrossStrategy,
}


def main():
    strategy_name = sys.argv[1] if len(sys.argv) > 1 else "gold_sma"
    symbol = sys.argv[2] if len(sys.argv) > 2 else "GLD"
    start_str = sys.argv[3] if len(sys.argv) > 3 else "2018-01-01"
    end_str = sys.argv[4] if len(sys.argv) > 4 else "2019-02-25"
    cash = float(sys.argv[5]) if len(sys.argv) > 5 else 100_000.0

    StrategyClass = STRAT_MAP.get(strategy_name, GoldSMAStrategy)
    strategy = StrategyClass()

    # Pick data source by market
    parsed = parse_symbol(symbol)
    if parsed.market.value in ("cn", "hk"):
        src = AkShareSource()
    else:
        src = YFinanceSource()

    bt = Backtester(
        symbols=[symbol],
        strategy=strategy,
        data_source=src,
        start=date.fromisoformat(start_str),
        end=date.fromisoformat(end_str),
        initial_cash=cash,
    )

    results = bt.run()
    results["strategy"] = strategy_name
    results["symbol"] = symbol
    results["start"] = start_str
    results["end"] = end_str

    # Save to results/
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    timestamp = date.today().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"backtest_{strategy_name}_{timestamp}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, default=str, indent=2, ensure_ascii=False)

    # Summary output
    summary = {
        "file": str(out_file),
        "final_equity": round(results["final_equity"], 2),
        "total_return_pct": round(results["total_return"] * 100, 2),
        "trades": len(results["trades"]),
        "commission": round(results["total_commission"], 2),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
