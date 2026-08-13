# WhaleTrail Scope — 基建定界

> 更新：2026-08-13

## 一句话

**低频率 paper trading：黄金主线，美股指数辅助对冲，A 股 watchlist 观察并逐步纳入低频率 paper；不做高频。**

## In scope

| 层级 | 内容 |
|------|------|
| 主资产 | 黄金：`GLD`（首选）、可选 `IAU`/`GC=F`/`SLV` |
| 辅资产 | 美股指数/个股：`SPY`、`QQQ`、`AAPL` 等 |
| A股（低频率） | tvscreener 快照积累；watchlist 观察为主，逐步纳入低频率 paper |
| 数据 | 日线 OHLCV（yfinance + Parquet 缓存）+ tvscreener 快照 |
| 引擎 | 事件驱动回测、模拟佣金（美股风格） |
| 策略 | gold_sma 为主；bollinger/turtle/momentum/ma_cross 对照 |
| 交付 | CLI、Streamlit 看板（`docs/DASHBOARD.md`）、Telegram 日报 cron |

## Out of scope

- 港股（暂不纳入）
- 分钟线 / tick / 高频
- 实盘下单（暂无交易账号）
- LEAN / Docker / 东方财富爬虫

## 数据流（定稿）

```
yfinance ──► ParquetCache ──► Backtester ──► results/*.json
                                      │
                                      ├── dashboard.py (:8766)
                                      └── daily-report → Ollama → Telegram
```

## 默认参数

| 项 | 默认 |
|----|------|
| 主标的 | `GLD` |
| 主策略 | `gold_sma` |
| 对冲对照 | `SPY` / `QQQ` |
| 回测区间 | 2018-01-01 → 近端 |
| 初始资金 | 100_000 USD |
| 佣金 | 5 bps，无最低 5 元 |

## 决策记录

1. 放弃 A股：akshare/东财不稳定，且策略重心不在 A股。
2. 放弃港股：同上，减少分叉。
3. 黄金用 `GLD` 而非 `GC=F`：ETF 连续日线更稳，paper 更友好。
4. 美股保留：作为对冲与相对强弱，不是主战场。
5. A 股纳入低频率 paper trading 目标（2026-08-13）：数据走 tvscreener 快照积累成日线，不走 yfinance 历史回测；稳定性受限，不追求高频。

## 决策记录规范

- 每个重大决策写一条，带日期；一句话说清"定了什么、为什么、影响哪里"。
- 决策若由代码执行，注明代码位置（如 `whaletrail/engine/broker.py`），不要重复抄数字。
- 新会话改业务边界前，先读本节；改完同步更新。
