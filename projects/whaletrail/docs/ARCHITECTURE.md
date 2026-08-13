# Architecture — 代码逻辑不变量

> 本文档记录代码层面"不能违反"的约定，避免跨会话实现冲突。业务边界见 SCOPE.md，运行环境见 ENVIRONMENT.md。

## 模块地图

```
whaletrail/
├── data/          DataLayer 门面 + yfinance(历史) + tvscreener(快照) + Parquet 缓存 + watchlist
├── engine/        事件驱动回测（Backtester / Broker / Account / Clock / Event）
├── strategy/      策略基类 + 注册表 + 6 个策略
├── metrics/       收益/回撤/夏普/胜率/盈亏比（FIFO 计算 PnL）
├── reporting/     watchlist Markdown 报表
├── storage/       SQLite（runs / trades / portfolio_snapshots / quote_snapshots）
└── indicators.py  共享指标（sma / atr / cross_signal）
```

## 数据流（定稿）

```
yfinance ─► YFinanceSource ─► ParquetCache(data_cache/) ─► Backtester ─► results/*.json
                                                               │             └► SQLite whaletrail.db
                                                               ├─ dashboard.py (:8766)
                                                               └─ daily-report.sh ─► analyze.py ─► Telegram

tvscreener ─► TVScreenerSource ─► quote_snapshots ─► watchlist_report.md
```

## 数据层组合

两个数据源按角色组合，不做朴素 fallback：

| 用途 | 主源 | 说明 |
|------|------|------|
| 历史日线（回测） | yfinance + Parquet 缓存 | tvscreener 不提供历史；缓存做覆盖检查 + 头尾补缺口，减少 yfinance 配额 |
| 实时快照 / watchlist / A股 | tvscreener | `get_quotes`；快照积累进 `quote_snapshots` 表 |
| paper-live 5m 信号 | yfinance | 实时扫描仍走 yfinance |

入口：`whaletrail/data/layer.py` 的 `DataLayer`。快照源的 yfinance fallback 是待办（需 tv/yahoo 符号映射）。

## 引擎不变量（重要）

1. **无前视偏差顺序**（`backtester._process_day`）：
   1. 成交昨日挂单（按今日 open）
   2. 喂今日 bar 给策略（新订单进 `pending_orders`）
   3. 挂单提交给 broker，次日执行
   4. 记录当日 equity 快照
2. **市场单按 open 成交**；限价单在 bar 的 high/low 范围内按限价成交。
3. **全额成交**（无部分成交）；佣金 `max(0.0005 * qty * price, 0)`，无滑点。
4. **Account**：`equity = cash + Σ(position qty * latest_price)`；买扣现金，卖加现金，佣金累加 `total_commission`。
5. **数据源协议**：`get_daily(symbol, start, end) -> DataFrame`，列 `open/high/low/close/volume`，索引 `DatetimeIndex` 升序、tz-naive。

## 策略

- 基类 `Strategy`：实现 `on_bar`；用 `buy` / `sell` / `order_target_percent` 下单；`pending_orders` 每 bar 被引擎清空。
- 注册表 `strategy/registry.py` 是**唯一**策略来源：`STRATEGY_CLASSES`（回测用）+ `_build_signal_registry()`（paper-live 信号用）。新增策略两处都要登记。
- `gold_sma`：SMA 20/50；金叉 → 目标仓位 80%；死叉 → 0%。

## 标的与市场边界

- `parse_symbol`（`data/symbols.py`）是 yfinance 回测标的守门人：**拒绝** A 股（`\d{6}.(SH|SZ)`）和港股（`\d{1,5}.HK`）。这只约束 yfinance 历史回测路径。
- A 股低频率 paper 走 tvscreener 快照积累（`quote_snapshots`），不走 yfinance；不要把 A 股 yahoo 代码接进 yfinance 回测。
- 港股暂不纳入。

## 缓存

- `ParquetCache`：`data_cache/<symbol>.parquet`，按日期 upsert（新行覆盖旧行）；文件名字符 `/`、`\`、`:` 替换为 `_`。
- yfinance 的 `GC=F` 等期货用 `auto_adjust=False`，其余 `auto_adjust=True`。

## 存储

- SQLite `results/whaletrail.db`（WAL）：`runs`、`trades`、`portfolio_snapshots`、`quote_snapshots`。
- `runs.symbols`、`metrics_json`、`positions_json`、`raw_json` 为 JSON 文本。
- 回测结果 JSON：`trades[]`（含 FIFO 计算的 `pnl`）、`equity_curve[]`、`final_equity`、`total_commission`、`total_return`、`metrics`、`strategy`、`symbol`、`role`、`market`、`start`、`end`。

## 指标约定

- `calculate_metrics`：252 交易日年化；无风险利率 2%；夏普 / 回撤 / 胜率 / 盈亏比。
- `compute_trade_pnl`：FIFO 配对卖单与最早买单，卖单带 `pnl` / `pnl_per_share`。
