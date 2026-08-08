## ⚠️ LEGACY — 黄金策略已迁移至 whaletrail/

此目录保留作为历史参考。LEAN 引擎已不再使用。
新入口: ~/Projects/shenkuo-misc/projects/whaletrail/
策略: whaletrail/strategy/strategies/gold_sma.py

运行回测:
  cd ~/Projects/shenkuo-misc/projects/whaletrail
  HTTPS_PROXY=http://127.0.0.1:7890 .venv/bin/python3 -m whaletrail.cli backtest run --strategy gold_sma --symbols GLD --start 2018-01-01 --end 2019-02-25

