# Gold Paper Trading

XAUUSD 黄金 paper trading 子项目，融合进沈括杂记 (`shenkuo-misc`)，由 OpenClaw + Telegram 驱动通报与决策分析。

## 架构

```
Telegram (@iron_blade_bot)
        │
        ▼
OpenClaw Gateway (:18789)          Ollama (qwen3:4b) — 分析日报
        │
        ├─ cron: 工作日 08:30 触发 daily-report.sh
        │
        ▼
shenkuo-misc/projects/gold-paper/    ← 代码 & 看板（本仓库）
        │
        ├─ algorithm/   LEAN 策略 (SMA 20/50)
        ├─ scripts/     回测、看板、分析、通报
        └─ dashboard/   静态 HTML 看板

        │ symlink
        ▼
~/OpenClaw-PaperTrading/gold-xau/    ← LEAN workspace（数据 + lean.json）
```

| 组件 | 路径 | 职责 |
|------|------|------|
| 策略代码 | `algorithm/` | XAUUSD 双均线趋势策略 |
| 行情数据 | `~/OpenClaw-PaperTrading/data/` | OANDA XAUUSD CFD（日线 2006–2019） |
| LEAN 引擎 | Docker `quantconnect/lean` | 本地回测 |
| 看板 | `dashboard/output/index.html` | 回测指标 + 权益曲线 |
| 分析 | `scripts/analyze.py` | Ollama 生成中文决策摘要 |
| 看板生成 | `scripts/build_dashboard.py` | 从回测 JSON 生成 HTML |
| 通报 | `scripts/daily-report.sh` | 回测 → 分析 → Telegram |

## 快速开始

```bash
# 1. 初始化（创建 symlink + 检查环境）
~/projects/shenkuo-misc/projects/gold-paper/scripts/setup.sh

# 2. 启动 Docker Desktop，然后跑回测
~/projects/shenkuo-misc/projects/gold-paper/scripts/run-backtest.sh

# 3. 本地看板
~/projects/shenkuo-misc/projects/gold-paper/scripts/serve-dashboard.sh
# → http://127.0.0.1:8765/

# 4. 手动发 Telegram 日报
~/projects/shenkuo-misc/projects/gold-paper/scripts/daily-report.sh

# 5. 注册工作日自动 cron
~/projects/shenkuo-misc/projects/gold-paper/openclaw/setup-cron.sh
```

## 策略说明

- **标的**: XAUUSD (OANDA CFD)
- **周期**: 日线
- **逻辑**: SMA(20) 上穿 SMA(50) 做多 80%，下穿清仓
- **回测区间**: 2018-01-01 → 2019-02-25（匹配本地数据）

后续可 `lean data download` 补充近期分钟线数据。

## 看板

两层看板并存，不冲突：

1. **Gold 专用看板** — `http://127.0.0.1:8765/`（本项目的回测指标、权益曲线）
2. **OpenClaw Gateway** — `http://127.0.0.1:18789/`（Agent 状态、会话、cron）

## OpenClaw 集成

- `~/.openclaw/workspace/TOOLS.md` — 路径索引
- `~/.openclaw/workspace/HEARTBEAT.md` — 周期性健康检查
- Cron job `gold-paper-daily` — 工作日 08:30 自动回测 + Telegram 通报

也可在 Telegram 直接问 Ironblade：
> "跑一下黄金回测" / "发 gold paper 日报"

## 数据扩展

```bash
cd ~/OpenClaw-PaperTrading
lean data download --dataset "CFD Data" \
  --data-type Quote --resolution Minute \
  --tickers XAUUSD --start 20190101 --end 20190225
```

## 相关路径

| 路径 | 说明 |
|------|------|
| `~/projects/shenkuo-misc/projects/gold-paper/` | 本仓库（代码源） |
| `~/OpenClaw-PaperTrading/` | LEAN workspace + 数据 |
| `~/github/Lean/` | LEAN 引擎源码 |
| `~/.openclaw/` | OpenClaw 运行时 |