# WhaleTrail Lab 🐋

> 跟庄者，顺流而行。不预测风暴，只辨认鲸鱼的尾迹。

**whaletrail-lab** 是一个以量化交易为锚点的个人实验空间。核心命题：用数据和系统对抗情绪，在被市场教训的过程中持续迭代。

不追求完美策略，追求的是：**跑起来 → 看到结果 → 改 → 再跑**。所有代码一步步在 Mac mini 上搭出来，Grok 协作开发，Telegram 日报盯着。

## 核心精神

- **数据说话。** 回测不撒谎。策略漂亮不算，曲线好才算。
- **系统化。** 手动盯盘太累，让脚本替你跑。paper-live 每 10 分钟 tick 一次，cron 每天推送日报。
- **跟庄，不造势。** 大资金走过的水域会留下痕迹。情绪扫描、KOL 追踪、量价信号，都是为了看清鲸鱼尾巴。
- **小步快跑。** 一个策略 + 一条标线 + 一份日报，验证完再扩展。黄金还没做明白之前，别碰 A 股。

## 当前重心

| 方向 | 说明 |
|------|------|
| **黄金 GLD** 主策略 | SMA 交叉、ATR 止损、持续迭代 |
| **美股对冲** SPY / QQQ | 对照实验，非高频 |
| **情绪扫描** | X/Twitter KOL 情绪 → 打分 → 信号融合 |
| **日报 / 看板** | OpenClaw + Telegram 推送；Streamlit 本地看板 `:8766` |
| **严格不做** | A 股、港股、分钟级/tick 高频、akshare/Tushare、LEAN/Docker |
| **Watchlist 快照** | TradingView scanner → YAML 关注列表 → SQLite → Markdown 报表 |

## 目录结构

```
.
├── projects/
│   └── whaletrail/            ← 唯一 active 项目
│       ├── whaletrail/        # 核心引擎（策略、回测、存储、风控）
│       ├── scripts/           # run-backtest / daily-report / paper-live / dashboard / sentiment
│       ├── config/            # watchlist.yaml
│       ├── reporting/        # Markdown 报表
│       ├── docs/              # SCOPE / SENTIMENT / WHALE_WATCH / tvscreener
│       ├── data_cache/        # yfinance Parquet 缓存（不入 git）
│       └── results/           # 回测 / 情绪输出（不入 git）
├── configs/                   # 环境配置
├── archive/                   # 旧项目归档（LEAN、gold-paper 等）
└── notes/                     # 随想
```

## 开发规则

| 角色 | 路径 | 规则 |
|------|------|------|
| Mac mini 主开发 | `~/Projects/whaletrail-lab` | 唯一主源。开发、测试、提交、推送都在这。 |
| GitHub | `zzz562/whaletrail-lab` | 同步中枢。 |
| MacBook 查看副本 | `~/github_code/whaletrail-lab` | 默认只查看。刷新：`git fetch && git reset --hard origin/main && git clean -fd` |

---

**创建** 2026-05-30  
**环境** Mac Mini M4 (macOS 26) + Grok Build + OpenClaw + Ollama  
**VPS** 阿里云上海轻量（反向隧道）  
**运行手册** [macmini-runbook](https://github.com/zzz562/ValarMorghulis/blob/main/macmini-runbook/README.md)
