# Scripts

| 脚本 | 用途 | 调用方式 |
|------|------|----------|
| `run-backtest.py` | 回测入口，策略+标的+日期+本金 | CLI / cron |
| `paper-live.py` | 实时多策略扫描 + Telegram 推送 | launchd 守护 (`tick` / `loop`) |
| `daily-report.sh` | 日报：回测 → 摘要 → stdout | cron / 手动 |
| `analyze.py` | 回测结果格式化（日报子模块） | 被 daily-report.sh 调用 |
| `dashboard.py` | Streamlit 看板 `:8766` | 手动 / launchd |
| `sentiment.py` | X/Twitter KOL 情绪扫描 → Ollama 打分 | cron |
| `fetch-tvscreener-watchlist.py` | TradingView scanner 快照拉取 | cron / 手动 |
| `watchlist-report.py` | SQLite → Markdown watchlist 报表 | cron / 手动 |

策略注册表见 `whaletrail/strategy/registry.py`。
