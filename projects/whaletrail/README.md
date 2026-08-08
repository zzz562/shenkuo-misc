# WhaleTrail — 统一 Paper Trading 平台

> 金刃 + 多市场回测，纯 Python 事件驱动，OpenClaw + Telegram 集成。

## 快速开始

```bash
cd ~/Projects/shenkuo-misc/projects/whaletrail

# 装依赖
.venv/bin/pip install -r requirements.txt

# 拉数据
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python -m whaletrail.cli data fetch --symbol GLD --start 2020-01-01

# 跑回测
HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python -m whaletrail.cli backtest run \
    --strategy gold_sma --symbols GLD --start 2018-01-01 --end 2019-02-25

# 列出策略
.venv/bin/python -m whaletrail.cli strategy list
```

## 策略

| 策略 | 文件 | 说明 |
|------|------|------|
| gold_sma | strategies/gold_sma.py | SMA 20/50 黄金趋势 |
| ma_cross | strategies/ma_cross.py | 通用双均线（可配周期） |

## 市场支持

| 市场 | 数据源 | 示例 |
|------|--------|------|
| 美股 | yfinance | AAPL, GLD, GC=F |
| A股 | akshare | 600519.SH |
| 港股 | akshare | 00700.HK |
