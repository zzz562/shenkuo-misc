#!/usr/bin/env python3
"""Format backtest results — direct data, no LLM (qwen3:4b hallucinated)."""
import json, sys
from pathlib import Path


def load_results(path):
    with open(path) as f:
        return json.load(f)


def main():
    rdir = Path(__file__).resolve().parent.parent / "results"
    files = sorted(rdir.glob("backtest_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print("⚠️ 无回测结果")
        sys.exit(1)

    r = load_results(str(files[0]))
    fe = r.get("final_equity", 0)
    ret = r.get("total_return", 0) * 100
    n = len(r.get("trades", []))
    strategy = r.get("strategy", "?")
    symbol = r.get("symbol", "?")

    # Format directly — no Ollama hallucination risk
    emoji = "📈" if ret > 0 else "📉" if ret < 0 else "➖"
    print(
        f"{emoji} {symbol} {strategy} "
        f"收益: {ret:+.2f}%  |  权益: ${fe:,.2f}  |  交易: {n}次"
    )


if __name__ == "__main__":
    main()
