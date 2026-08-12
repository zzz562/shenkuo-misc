#!/usr/bin/env bash
# WhaleTrail daily report: backtest -> direct summary -> markdown output
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
PY="$ROOT/.venv/bin/python3"

# Proxy fallback: try configured proxy, continue without if unavailable
if curl -s --connect-timeout 2 --max-time 3 -x http://127.0.0.1:7890 https://www.google.com > /dev/null 2>&1; then
    export HTTPS_PROXY=http://127.0.0.1:7890
else
    # Try without proxy (direct connection or system proxy)
    unset HTTPS_PROXY
    # If yfinance still needs proxy, it'll fail with a clear error
fi

echo "🥇 **WhaleTrail 日报**"
echo ""

# Step 1: run backtest
echo "⏳ 回测中..."
# Defaults: gold_sma on GLD (primary universe)
BT_JSON=$("$PY" "$SCRIPTS/run-backtest.py" "${1:-gold_sma}" "${2:-GLD}" "${3:-2018-01-01}" "${4:-2026-08-12}" "${5:-100000}")

# Parse summary
FINAL_EQ=$(echo "$BT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['final_equity'])")
RETURN_PCT=$(echo "$BT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_return_pct'])")
TRADE_N=$(echo "$BT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['trades'])")

echo "📊 ${2:-GLD}  ${3:-2018-01-01} -> ${4:-2026-08-12}  (黄金主线)"
echo "💰 权益: \$${FINAL_EQ}  |  收益: ${RETURN_PCT}%  |  交易: ${TRADE_N}次"
echo ""

# Step 2: direct summary (no LLM — qwen3:4b hallucinated)
echo "📊 回测摘要..."
"$PY" "$SCRIPTS/analyze.py"

echo ""
echo "_自动生成 · WhaleTrail · $(date '+%Y-%m-%d %H:%M')_"
