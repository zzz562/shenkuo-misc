# Ironblade ↔ Mac Mini Bridge

Connects the Telegram bot **@iron_blade_bot** to this Mac Mini via **OpenClaw**.

## Architecture

```
You (Telegram) ──► @iron_blade_bot ──► OpenClaw Gateway (localhost:18789)
                                              │
                                              ├─► Ollama (qwen3:4b) — local LLM
                                              ├─► Agent workspace (~/.openclaw/workspace)
                                              └─► Tools: shell, files, web search, skills
```

OpenClaw is the bridge program — no separate bot daemon needed. It runs as a macOS LaunchAgent and polls Telegram for messages 24/7.

## Quick Start

```bash
# Check everything is healthy
~/projects/whaletrail-lab/projects/ironblade-mac-bridge/health-check.sh

# Send a test message to yourself on Telegram
openclaw message send --channel telegram --target 5102138680 --message "ping"

# Open local dashboard
open http://127.0.0.1:18789/
```

## Talk to Ironblade

1. Open Telegram and message **@iron_blade_bot**
2. If first time: send any message → bot replies with a pairing code
3. Approve on Mac: `openclaw pairing approve telegram <code>`
4. You're paired — messages route to the Mac Mini agent

## Key Paths

| What | Where |
|------|-------|
| OpenClaw config | `~/.openclaw/openclaw.json` |
| Agent workspace | `~/.openclaw/workspace/` |
| Gateway logs | `~/.openclaw/logs/gateway.log` |
| Telegram allowlist | `~/.openclaw/credentials/telegram-default-allowFrom.json` |
| LaunchAgent | `~/Library/LaunchAgents/ai.openclaw.gateway.plist` |

## Services

```bash
# Gateway (Telegram bridge + agent)
openclaw gateway status
openclaw gateway restart

# Ollama (local LLM — must be running for bot replies)
brew services start ollama
ollama list

# Optional: Mac node host for deeper device control
openclaw node install
openclaw node start
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Bot doesn't reply | Check Ollama: `brew services start ollama` |
| Polling stalls in logs | Network issue; `openclaw gateway restart` |
| "Pairing required" | `openclaw pairing list` then `approve` |
| Group messages ignored | Add your Telegram ID to `groupAllowFrom` in config |

## Security Notes

- Bot token and API keys live in `~/.openclaw/openclaw.json` — never commit these
- DM policy: `pairing` (unknown users must approve first)
- Gateway binds to `127.0.0.1` only (local access)
- Paired user: `@zephyrval` (ID `5102138680`)