#!/usr/bin/env bash
# WhaleTrail daily report: backtest -> Ollama analysis -> markdown output
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
PY="$ROOT/.venv/bin/python3"
export HTTPS_PROXY=http://127.0.0.1:7890

echo "🥇 **WhaleTrail 日报**"
echo ""

# Step 1: run backtest
echo "⏳ 回测中..."
BT_JSON=$("$PY" "$SCRIPTS/run-backtest.py" "${1:-gold_sma}" "${2:-GLD}" "${3:-2018-01-01}" "${4:-2019-02-25}" "${5:-100000}")

# Parse summary
FINAL_EQ=$(echo "$BT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['final_equity'])")
RETURN_PCT=$(echo "$BT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['total_return_pct'])")
TRADE_N=$(echo "$BT_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['trades'])")

echo "📊 ${2:-GLD}  ${3:-2018-01-01} -> ${4:-2019-02-25}"
echo "💰 权益: \$${FINAL_EQ}  |  收益: ${RETURN_PCT}%  |  交易: ${TRADE_N}次"
echo ""

# Step 2: Ollama analysis
echo "🤖 AI 分析..."
"$PY" "$SCRIPTS/analyze.py"

echo ""
echo "_自动生成 · WhaleTrail · $(date '+%Y-%m-%d %H:%M')_"
