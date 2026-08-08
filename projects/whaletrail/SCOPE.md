# WhaleTrail Scope — 基建定界

> 更新：2026-08-08

## 一句话

**把黄金做明白；美股指数只做辅助对冲；不做 A股/港股/高频。**

## In scope

| 层级 | 内容 |
|------|------|
| 主资产 | 黄金：`GLD`（首选）、可选 `IAU`/`GC=F`/`SLV` |
| 辅资产 | 美股指数/个股：`SPY`、`QQQ`、`AAPL` 等 |
| 数据 | 日线 OHLCV，yfinance + 本地 Parquet 缓存 |
| 引擎 | 事件驱动回测、模拟佣金（美股风格） |
| 策略 | gold_sma 为主；bollinger/turtle/momentum/ma_cross 对照 |
| 交付 | CLI、Streamlit 看板、Telegram 日报 cron |

## Out of scope

- A股、港股（数据源不稳 + 不是当前目标）
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
