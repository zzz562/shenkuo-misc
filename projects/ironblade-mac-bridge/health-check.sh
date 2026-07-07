#!/usr/bin/env bash
# Ironblade ↔ Mac Mini health check
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; FAIL=1; }

FAIL=0
echo "Ironblade ↔ Mac Mini Health Check"
echo "=================================="
echo ""

# OpenClaw CLI
if command -v openclaw &>/dev/null; then
  ok "OpenClaw installed ($(openclaw --version 2>/dev/null | head -1))"
else
  fail "OpenClaw not found in PATH"
fi

# Gateway
if openclaw gateway status 2>/dev/null | grep -q "Runtime: running"; then
  ok "Gateway running"
else
  fail "Gateway not running — run: openclaw gateway restart"
fi

# Telegram channel
if openclaw channels status 2>/dev/null | grep -qi "telegram.*running"; then
  ok "Telegram channel active (@iron_blade_bot)"
else
  fail "Telegram channel not running"
fi

# Ollama
if curl -sf http://127.0.0.1:11434/api/tags &>/dev/null; then
  MODELS=$(curl -sf http://127.0.0.1:11434/api/tags | python3 -c "import sys,json; print(', '.join(m['name'] for m in json.load(sys.stdin).get('models',[])))" 2>/dev/null || echo "unknown")
  ok "Ollama running (models: ${MODELS})"
else
  fail "Ollama not running — run: brew services start ollama"
fi

# Paired user
if [[ -f "$HOME/.openclaw/credentials/telegram-default-allowFrom.json" ]]; then
  PAIRED=$(python3 -c "import json; print(', '.join(json.load(open('$HOME/.openclaw/credentials/telegram-default-allowFrom.json'))['allowFrom']))" 2>/dev/null || echo "?")
  ok "Paired Telegram users: ${PAIRED}"
else
  warn "No Telegram allowlist file found"
fi

# Recent errors
ERR_LOG="$HOME/.openclaw/logs/gateway.err.log"
if [[ -f "$ERR_LOG" ]]; then
  RECENT_ERRS=$(tail -50 "$ERR_LOG" | grep -c "error\|stall\|timeout" || true)
  if [[ "$RECENT_ERRS" -gt 3 ]]; then
    warn "Recent gateway errors detected ($RECENT_ERRS in last 50 lines) — check $ERR_LOG"
  else
    ok "No recent critical errors in gateway log"
  fi
fi

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo -e "${GREEN}All checks passed.${NC} Message @iron_blade_bot on Telegram to test."
else
  echo -e "${RED}Some checks failed.${NC} See messages above."
  exit 1
fi