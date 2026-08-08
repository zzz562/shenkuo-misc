#!/usr/bin/env python3
"""Ollama analysis — uses CLI, strips thinking for clean Telegram output."""
import json, subprocess, sys, re
from pathlib import Path

MODEL = "qwen3:4b"


def load_results(path):
    with open(path) as f:
        return json.load(f)


def call_ollama(prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", MODEL, prompt],
        capture_output=True, text=True, timeout=180,
        env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin",
             "HOME": str(Path.home())},
    )
    raw = (result.stdout + result.stderr).strip()
    # Remove ANSI escape codes
    raw = re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]', '', raw)
    raw = re.sub(r'\x1b\[\d*[KG]', '', raw)
    # Remove spinner characters and "Thinking...done thinking." blocks
    raw = re.sub(r'[⠙⠹⠸⠼⠴⠦⠧⠇⠏⠋]', '', raw)
    raw = re.sub(r'^\s*Thinking\.\.\.[\s\S]*?done thinking\.\s*', '', raw, flags=re.DOTALL)
    # Remove "嗯" and other filler at the start
    raw = re.sub(r'^嗯[,，]?\s*', '', raw)
    return raw.strip()


def main():
    rdir = Path(__file__).resolve().parent.parent / "results"
    files = sorted(rdir.glob("backtest_*.json"), reverse=True)
    if not files:
        print("no results found")
        sys.exit(1)

    r = load_results(str(files[0]))
    trades = r.get("trades", [])
    fe = r.get("final_equity", 0)
    ret = r.get("total_return", 0) * 100

    prompt = (
        "你是金刃。用一句简洁中文（30字以内）总结回测结果。"
        "策略:{0} 标的:{1} {2}->{3} 权益:${4:,.0f} 收益:{5:.1f}% 交易:{6}次。"
        "直接输出结论，不要思考过程。".format(
            r.get("strategy", "?"),
            r.get("symbol", "?"),
            r.get("start", "?"),
            r.get("end", "?"),
            fe, ret, len(trades),
        )
    )

    raw = call_ollama(prompt)
    # If output is too long, take first meaningful sentence
    if len(raw) > 200:
        lines = [l for l in raw.split('\n') if len(l.strip()) > 3]
        raw = '\n'.join(lines[:3])
    print(raw if raw.strip() else "gold_sma GLD 2018-2019: +{:.1f}%, {} trades".format(ret, len(trades)))


if __name__ == "__main__":
    main()
