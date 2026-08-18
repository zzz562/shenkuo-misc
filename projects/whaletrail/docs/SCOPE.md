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
6. live paper 增加交易时段检查（2026-08-17）：`paper-live.py`（美股）与 `ashare-paper.py`（A股）此前不检查营业时间，周末也会扫描并更新 paper 仓位。现由 `whaletrail/engine/session.py` 统一门禁：美股 Mon–Fri 09:30–16:00 ET + K 线当日新鲜度兜底（覆盖节假日）；A股交易日+时段窗口。
7. A股节假日走深交所官方日历（2026-08-17）：周末排除无法覆盖十一/春节等长假。`ashare-paper.py` 交易日判断改用深交所官方接口 `whaletrail/data/trading_calendar.py`（含调休），缓存 `data_cache/trading_calendar_cn.txt`、按月增量拉取；未公告月份与断网时回退周一~五判断。美股已由 paper-live 的 K 线新鲜度兜底，无需日历。
8. Live 信号统一为已收盘日线（2026-08-18）：paper-live 此前用 5m K 线跑日线参数的策略，与回测验证的周期不是同一个东西。现拉 ~420 天日线，信号只用已收盘 bar、按当日开盘价记账（对齐回测"信号日收盘→次日开盘成交"）。日线信号每交易日上午扫一次即够，不再 5m 盯盘。代码：`scripts/paper-live.py`。
9. 回测数据加价格量纲门禁（2026-08-18）：发现 GLD 回测结果的价格是 GC=F 量级（2018 年 $1227–1340，真实 GLD 为 $113–131），缓存张冠李戴。`whaletrail/data/cache.py` 按 symbol 校验中位价区间（`PRICE_BOUNDS`），读写双向拦截；`scripts/verify-cache.py` 在 Mac mini 审计存量缓存并可用 `--drop-invalid` 清理。
10. A 股 paper 补交易规则与成本（2026-08-18）：信号=昨收、成交=今收（消除"信号价即成交价"的前视）；佣金万2.5（¥5 底）+ 卖出印花税 0.05% + 单边滑点 0.1%；涨跌停封板无法成交、挂单顺延（创业板/科创板 20%，主板 10%）；T+1；整手 100 股、每笔名义 ¥5 万。代码：`scripts/ashare-paper.py`。
11. Live 簿记按 (symbol, strategy) 隔离 + 行情质检（2026-08-18）：多策略此前共用 `positions["GLD"]` 互相踩踏，gold_sma_v2 的 ATR 止损被污染。仓位/止损 key 统一为 `symbol|strategy`（`whaletrail/strategy/base.py position_key`），旧 state 加载时自动迁移。行情经 `validate_daily`（bar 数 / 非正价 / 单日 >25% 异动）+ 跨标的同价检测，不合格不出信号。代码：`scripts/paper-live.py`。
12. 参数稳健性用网格验证（2026-08-18）：SMA 20/50 是否过拟合，用 `scripts/param-sweep.py` 的 fast×slow 网格 + B&H 基准判断：邻域成片为高原则可信，孤峰则过拟合。默认区间 2011 起，把 2011–2015 黄金熊市纳入样本。sweep 结果不写入 runs 表。

## 决策记录规范

- 每个重大决策写一条，带日期；一句话说清"定了什么、为什么、影响哪里"。
- 决策若由代码执行，注明代码位置（如 `whaletrail/engine/broker.py`），不要重复抄数字。
- 新会话改业务边界前，先读本节；改完同步更新。
