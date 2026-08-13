#!/usr/bin/env python3
"""WhaleTrail Dashboard — 回测 / 实时信号 / 情绪 / Watchlist / 运行状态."""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from whaletrail.metrics.performance import calculate_metrics, compute_trade_pnl
from whaletrail.storage.repository import Repository

st.set_page_config(page_title="WhaleTrail", layout="wide", page_icon="🐋")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = RESULTS_DIR / "whaletrail.db"
DATA_CACHE_DIR = ROOT / "data_cache"

SCORE_COLORS = {"bullish": "#16a34a", "bearish": "#dc2626", "neutral": "#6b7280"}
SCORE_EMOJI = {"bullish": "📈", "bearish": "📉", "neutral": "➖"}
SIDE_EMOJI = {"BUY": "🟢 买入", "SELL": "🔴 卖出", "buy": "🟢 买入", "sell": "🔴 卖出"}

st.markdown("""
<style>
.big-metric { font-size: 2.4rem; font-weight: 700; }
.sentiment-card { border-left: 4px solid #3b82f6; padding: 0.8rem 1rem; margin: 0.3rem 0; border-radius: 6px; background: #f8fafc; }
.tweet-body { font-size: 0.95rem; line-height: 1.5; color: #1e293b; }
.meta-row { color: #64748b; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# Fragment auto-refresh with graceful fallback for older streamlit versions.
# Set WHALETRAIL_NO_AUTOREFRESH=1 to disable the run_every timer (e.g. for
# AppTest runs, which do not simulate fragment timers reliably).
_fragment = getattr(st, "fragment", None)
_autorun_every = None if __import__("os").environ.get("WHALETRAIL_NO_AUTOREFRESH") else 60


def _frag(run_every: Optional[int] = None):
    if _fragment is None:
        return lambda f: f
    return _fragment(run_every=_autorun_every)


# ═══════════════════════════════════════════════════════════════════
#  Cached data loaders
# ═══════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def list_backtest_files() -> list[str]:
    files = sorted(
        RESULTS_DIR.glob("backtest_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [p.name for p in files]


@st.cache_data(ttl=60, show_spinner=False)
def load_backtest(name: str) -> dict:
    with open(RESULTS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=60, show_spinner=False)
def load_sentiment_latest() -> Optional[dict]:
    f = RESULTS_DIR / "sentiment_latest.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@st.cache_data(ttl=60, show_spinner=False)
def load_sentiment_history() -> list[dict]:
    out = []
    for f in sorted(RESULTS_DIR.glob("sentiment_*.json")):
        if f.name in ("sentiment_latest.json", "sentiment_state.json"):
            continue
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


@st.cache_data(ttl=60, show_spinner=False)
def load_live_state() -> Optional[dict]:
    f = RESULTS_DIR / "paper_live_state.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


@st.cache_data(ttl=60, show_spinner=False)
def load_quote_snapshots() -> list[dict]:
    try:
        repo = Repository(DB_PATH)
        rows = repo.latest_quote_snapshots()
        repo.close()
        return rows
    except Exception:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def latest_quote_ts() -> Optional[str]:
    try:
        repo = Repository(DB_PATH)
        ts = repo.latest_quote_timestamp()
        repo.close()
        return ts
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def load_cached_close(symbol: str) -> Optional[pd.DataFrame]:
    """Read a symbol's cached daily closes from data_cache (offline)."""
    safe = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
    path = DATA_CACHE_DIR / f"{safe}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    if df.empty:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


# ═══════════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════════
def _staleness(ts_str: str) -> str:
    if not ts_str:
        return "?"
    try:
        ts = pd.to_datetime(ts_str)
        if pd.isna(ts):
            return "?"
        age = datetime.now() - ts.to_pydatetime()
        secs = int(age.total_seconds())
        if secs < 0:
            return "时间异常"
        if secs < 90:
            return f"{secs}s 前"
        if secs < 3600:
            return f"{secs // 60} 分钟前"
        if secs < 86400:
            return f"{secs // 3600} 小时前"
        return f"{secs // 86400} 天前"
    except Exception:
        return "?"


def _backtest_metrics(data: dict) -> tuple[list[dict], dict, float]:
    """Return (enriched_trades, metrics, initial_cash), computing on the fly
    when the JSON was written before metrics were persisted."""
    trades_raw = data.get("trades", [])
    if trades_raw and "pnl" in (trades_raw[0] or {}):
        enriched = trades_raw
    else:
        enriched = compute_trade_pnl(trades_raw)
    metrics = data.get("metrics")
    initial_cash = 100_000.0
    if not metrics:
        fe = float(data.get("final_equity", 0) or 0)
        tr_frac = float(data.get("total_return", 0) or 0)
        if 1 + tr_frac > 0:
            initial_cash = fe / (1 + tr_frac)
        equity = [p["equity"] for p in data.get("equity_curve", [])]
        metrics = calculate_metrics(enriched, equity, initial_cash)
    return enriched, metrics, initial_cash


def _benchmark_series(data: dict, initial_cash: float) -> Optional[pd.Series]:
    """Buy-and-hold series for the backtest symbol, from local cache only."""
    symbol, start, end = data.get("symbol"), data.get("start"), data.get("end")
    if not symbol or not start or not end:
        return None
    df = load_cached_close(symbol)
    if df is None:
        return None
    try:
        b = df.loc[pd.Timestamp(start): pd.Timestamp(end)]
        if b.empty or len(b) < 2:
            return None
        first = float(b["close"].iloc[0])
        if first <= 0:
            return None
        s = (b["close"] / first * initial_cash).rename("买入持有")
        s.index = pd.to_datetime(s.index)
        return s
    except Exception:
        return None


def _parse_signals(mapping: dict) -> list[dict]:
    rows = []
    for key, ts in (mapping or {}).items():
        parts = key.split("|")
        if len(parts) == 3:
            rows.append({"symbol": parts[0], "strategy": parts[1], "side": parts[2], "date": str(ts)[:10]})
    return rows


def _signal_tags(r: dict) -> str:
    tags = []
    rsi = r.get("rsi")
    if rsi is not None:
        if rsi >= 70:
            tags.append("RSI 超买")
        elif rsi <= 30:
            tags.append("RSI 超卖")
    close, s200 = r.get("close"), r.get("sma200")
    if close and s200:
        tags.append("多头" if close > s200 else "空头")
    return " · ".join(tags) if tags else "—"


def _service_checks() -> list[dict]:
    checks = {
        "OpenClaw Gateway": ("http://127.0.0.1:18789/health", 18789),
        "Dashboard": ("http://127.0.0.1:8766", 8766),
        "Ollama": ("http://127.0.0.1:11434/api/tags", 11434),
    }
    rows = []
    for name, (url, port) in checks.items():
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                rows.append({"服务": name, "端口": str(port), "状态": "✅" if r.status < 400 else "⚠️"})
        except Exception:
            rows.append({"服务": name, "端口": str(port), "状态": "❌"})
    return rows


def _launchd_rows() -> list[dict]:
    rows = []
    try:
        out = subprocess.check_output(["launchctl", "list"], text=True, timeout=5)
    except Exception:
        return rows
    for label, display in [
        ("ai.whaletrail-live", "Paper Live"),
        ("homebrew.mxcl.ollama", "Ollama"),
        ("ai.openclaw.gateway", "OpenClaw Gateway"),
    ]:
        rows.append({"服务": f"launchd: {display}", "端口": "-", "状态": "✅" if label in out else "❌"})
    return rows


def _runs_count() -> int:
    try:
        repo = Repository(DB_PATH)
        n = len(repo.list_runs(limit=1000))
        repo.close()
        return n
    except Exception:
        return -1


# ═══════════════════════════════════════════════════════════════════
#  Page: 总览
# ═══════════════════════════════════════════════════════════════════
@_frag(run_every=60)
def _overview_panel() -> None:
    files = list_backtest_files()
    latest = load_backtest(files[0]) if files else None
    sent = load_sentiment_latest()
    live = load_live_state()
    snaps = load_quote_snapshots()

    c1, c2, c3, c4 = st.columns(4)
    if latest:
        enriched, metrics, _ = _backtest_metrics(latest)
        ret = metrics.get("total_return", 0.0)
        dd = metrics.get("max_drawdown", 0.0)
        c1.metric("最新回测收益", f"{ret:+.2f}%", delta=f"最大回撤 {dd:.2f}%")
        c2.metric("策略 · 标的", f"{latest.get('strategy', '?')} · {latest.get('symbol', '?')}",
                  f"交易 {len(enriched)} 次 · 结束 {latest.get('end', '?')}")
    else:
        c1.metric("最新回测收益", "—")
        c2.metric("策略 · 标的", "—", "运行 scripts/run-backtest.py")

    if sent:
        gsi = sent.get("gold_sentiment_index", 0.0)
        bull, bear = sent.get("bullish_count", 0), sent.get("bearish_count", 0)
        c3.metric("GSI 情绪指数", f"{gsi:+.3f}", f"📈 {bull} · 📉 {bear}")
    else:
        c3.metric("GSI 情绪指数", "—", "等待情绪扫描")

    if live:
        snap = live.get("last_snapshot") or {}
        gld = snap.get("GLD", {})
        price = gld.get("price")
        c4.metric("GLD 实时价格", f"${price:,.2f}" if price else "—",
                  _staleness(gld.get("ts", "")) if gld else None)
    else:
        c4.metric("GLD 实时价格", "—", "等待 paper-live")

    c5, c6, c7, c8 = st.columns(4)
    signals = _parse_signals((live or {}).get("last_signals") or {})
    today = date.today().isoformat()
    c5.metric("今日策略信号", sum(1 for s in signals if s["date"] == today), f"累计 {len(signals)} 条")
    rsi_alerts = [s for s in snaps if (s.get("rsi") is not None and (s["rsi"] >= 70 or s["rsi"] <= 30))]
    c6.metric("Watchlist 覆盖", len(snaps), f"RSI 极端 {len(rsi_alerts)} 只")
    services = _service_checks()
    c7.metric("服务健康", f"{sum(1 for r in services if r['状态'] == '✅')}/{len(services)}")
    runs = _runs_count()
    c8.metric("SQLite 回测记录", runs if runs >= 0 else "?")


def page_overview() -> None:
    st.title("📊 总览")
    _overview_panel()
    st.caption("总览每 60s 自动刷新 · 数据源: results/*.json + results/whaletrail.db")


# ═══════════════════════════════════════════════════════════════════
#  Page: 回测结果
# ═══════════════════════════════════════════════════════════════════
def page_backtest() -> None:
    st.title("📈 回测结果")
    files = list_backtest_files()
    if not files:
        st.info("还没有回测结果。运行 scripts/run-backtest.py 生成。")
        return
    selected = st.selectbox("选择回测", files)
    data = load_backtest(selected)
    enriched, metrics, initial_cash = _backtest_metrics(data)

    fe = float(data.get("final_equity", 0) or 0)
    trades_n = len(enriched)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最终权益", f"${fe:,.0f}", f"初始 ${initial_cash:,.0f}")
    c2.metric("总收益率", f"{metrics.get('total_return', 0):+.2f}%")
    c3.metric("年化收益率", f"{metrics.get('annual_return', 0):+.2f}%")
    c4.metric("最大回撤", f"{metrics.get('max_drawdown', 0):.2f}%")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Sharpe", f"{metrics.get('sharpe_ratio', 0):.2f}")
    c6.metric("胜率", f"{metrics.get('win_rate', 0) * 100:.1f}%")
    c7.metric("盈亏比", f"{metrics.get('profit_factor', 0):.2f}")
    c8.metric("交易次数", trades_n, f"手续费 ${data.get('total_commission', 0):.2f}")
    st.caption(f"策略: **{data.get('strategy', '?')}** · 标的: {data.get('symbol', '?')} · "
               f"{data.get('start', '?')} → {data.get('end', '?')}")

    equity = data.get("equity_curve", [])
    if equity:
        df_eq = pd.DataFrame(equity)
        df_eq["date"] = pd.to_datetime(df_eq["date"])
        df_eq = df_eq.set_index("date")
        bench = _benchmark_series(data, initial_cash)
        if bench is not None:
            df_eq = df_eq.join(bench, how="left")
        st.subheader("权益曲线")
        st.line_chart(df_eq, height=320)
        if bench is not None:
            st.caption("橙色线为买入持有对照（数据来自本地 data_cache 缓存）")

        st.subheader("回撤")
        dd = (df_eq["equity"] / df_eq["equity"].cummax() - 1) * 100
        st.area_chart(pd.DataFrame({"回撤%": dd}), height=220, color="#dc2626")

    if enriched:
        st.subheader("交易记录")
        df_t = pd.DataFrame(enriched)
        if "date" in df_t.columns:
            df_t["date"] = pd.to_datetime(df_t["date"]).dt.date
        cols = [c for c in ("date", "symbol", "side", "quantity", "price", "commission", "pnl") if c in df_t.columns]
        st.dataframe(
            df_t[cols], width="stretch", hide_index=True,
            column_config={
                "price": st.column_config.NumberColumn("价格", format="$%.2f"),
                "commission": st.column_config.NumberColumn("手续费", format="$%.2f"),
                "pnl": st.column_config.NumberColumn("已实现盈亏", format="$%.2f"),
            },
        )
        sells = [t for t in enriched if str(t.get("side", "")).lower() == "sell"]
        wins = sum(1 for t in sells if (t.get("pnl") or 0) > 0)
        losses = sum(1 for t in sells if (t.get("pnl") or 0) < 0)
        st.caption(f"平仓 {len(sells)} 笔 · 盈利 {wins} · 亏损 {losses}")

    # ── Cross-run comparison ─────────────────────────────────────────
    if len(files) > 1:
        st.subheader("跨回测对比")
        rows = []
        for name in files:
            d = load_backtest(name)
            m = d.get("metrics")
            rows.append({
                "文件": name,
                "策略": d.get("strategy", "?"),
                "标的": d.get("symbol", "?"),
                "结束日": d.get("end", "?"),
                "总收益%": m.get("total_return") if m else round((d.get("total_return", 0) or 0) * 100, 2),
                "最终权益": round(float(d.get("final_equity", 0) or 0), 2),
                "交易次数": len(d.get("trades", [])),
                "最大回撤%": m.get("max_drawdown") if m else None,
                "Sharpe": m.get("sharpe_ratio") if m else None,
            })
        df_cmp = pd.DataFrame(rows)
        st.dataframe(df_cmp, width="stretch", hide_index=True)
        cmp_chart = df_cmp.head(10).copy()
        cmp_chart["label"] = cmp_chart["策略"] + " · " + cmp_chart["标的"] + " · " + cmp_chart["结束日"].astype(str)
        st.bar_chart(cmp_chart.set_index("label")["总收益%"], height=240)


# ═══════════════════════════════════════════════════════════════════
#  Page: 实时信号
# ═══════════════════════════════════════════════════════════════════
@_frag(run_every=60)
def _live_panel() -> None:
    live = load_live_state()
    if not live:
        st.info("还没有实时扫描数据。运行 scripts/paper-live.py tick（或 loop --interval 600）")
        return

    snap = live.get("last_snapshot") or {}
    cols = st.columns(max(1, len(snap)))
    for col, (sym, info) in zip(cols, snap.items()):
        price = info.get("price")
        col.metric(sym, f"${price:,.2f}" if price else "?", _staleness(info.get("ts", "")))

    signals = _parse_signals(live.get("last_signals") or {})
    if signals:
        df_s = pd.DataFrame(signals)
        today = date.today().isoformat()
        df_s["今日"] = df_s["date"] == today
        df_s["方向"] = df_s["side"].map(SIDE_EMOJI).fillna(df_s["side"])
        st.subheader(f"策略信号 · 共 {len(df_s)} 条 · 今日 {int(df_s['今日'].sum())} 条")
        st.dataframe(
            df_s[["symbol", "strategy", "方向", "date", "今日"]],
            width="stretch", hide_index=True,
            column_config={"今日": st.column_config.CheckboxColumn("今日")},
        )
    else:
        st.info("暂无信号记录")

    positions = live.get("positions") or {}
    if positions:
        st.subheader("当前持仓")
        if isinstance(positions, dict):
            st.dataframe(pd.DataFrame(positions).T, width="stretch")
        else:
            st.dataframe(pd.DataFrame(positions), width="stretch")
    else:
        st.caption("当前无持仓")


def page_live() -> None:
    st.title("🔴 实时信号")
    _live_panel()
    st.caption("状态文件: results/paper_live_state.json · 信号面板每 60s 自动刷新")


# ═══════════════════════════════════════════════════════════════════
#  Page: 情绪监控
# ═══════════════════════════════════════════════════════════════════
def page_sentiment() -> None:
    st.title("🐋 Gold Sentiment Index")
    latest = load_sentiment_latest()
    if not latest:
        st.info("等待首次情绪扫描（cron: whaletrail-sentiment 每日 09:00）")
        return

    gsi = latest.get("gold_sentiment_index", 0.0)
    bullish = latest.get("bullish_count", 0)
    bearish = latest.get("bearish_count", 0)
    neutral = latest.get("neutral_count", 0)
    total = latest.get("total_scored", 0)
    entries = latest.get("entries", [])

    tag = "🟢 看多" if gsi > 0.15 else ("🔴 看空" if gsi < -0.15 else "🟡 中性")
    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 2])
    c1.metric("GSI 情绪指数", f"{gsi:+.3f}", tag)
    c2.metric("📈 看多", bullish)
    c3.metric("📉 看空", bearish)
    c4.metric("➖ 中性", neutral)
    c5.metric("📊 扫描", f"{total} 条推文")
    kols = latest.get("scanned_kols") or len({e.get("account") for e in entries})
    st.caption(f"数据日期: **{latest.get('date', '?')}** · 覆盖 KOL: {kols} 位 · 每日 09:00 更新")

    history = load_sentiment_history()
    if history:
        st.subheader("📊 GSI 历史趋势")
        df_h = pd.DataFrame(history).sort_values("date")
        df_h["date"] = pd.to_datetime(df_h["date"])
        df_h = df_h.set_index("date")

        source = df_h.reset_index()
        source["GSI"] = source["gold_sentiment_index"]
        source["Bullish"] = source["bullish_count"]
        source["Bearish"] = source["bearish_count"]

        bar = alt.Chart(source).mark_bar(opacity=0.3).encode(
            x="date:T", y="Bullish:Q", color=alt.value("#16a34a"),
        ).properties(height=250)
        bar2 = alt.Chart(source).mark_bar(opacity=0.3).encode(
            x="date:T", y=alt.Y("Bearish:Q", scale=alt.Scale(domain=[0, source["Bearish"].max() + 1])),
            color=alt.value("#dc2626"),
        )
        line = alt.Chart(source).mark_line(point=True, color="#3b82f6", strokeWidth=3).encode(
            x="date:T",
            y=alt.Y("GSI:Q", scale=alt.Scale(domain=[-1, 1])),
            tooltip=["date", "GSI", "Bullish", "Bearish"],
        ).properties(height=250)

        st.altair_chart((bar + bar2 + line).resolve_scale(y="independent"), width="stretch")

        st.caption("每日汇总")
        tbl = source[["date", "GSI", "Bullish", "Bearish", "neutral_count"]].rename(
            columns={"neutral_count": "Neutral"}
        ).tail(10)
        st.dataframe(tbl.set_index("date"), width="stretch")

    if entries:
        col_left, col_right = st.columns([1, 2])
        with col_left:
            st.subheader("情绪分布")
            df_dist = pd.DataFrame({"方向": ["📈 看多", "📉 看空", "➖ 中性"], "数量": [bullish, bearish, neutral]})
            st.bar_chart(df_dist.set_index("方向"), width="stretch")

            kol_rows = []
            for acc, grp in pd.DataFrame(entries).groupby("account"):
                kol_rows.append({
                    "KOL": acc,
                    "看多": int((grp["score"] == "bullish").sum()),
                    "看空": int((grp["score"] == "bearish").sum()),
                    "中性": int((grp["score"] == "neutral").sum()),
                    "均置信": round(float(grp["confidence"].mean()), 1),
                })
            st.caption(f"覆盖 KOL: {len(kol_rows)} 位")
            st.dataframe(pd.DataFrame(kol_rows), width="stretch", hide_index=True)

            kw = Counter(e.get("keyword", "") for e in entries)
            st.caption("关键词分布")
            st.dataframe(
                pd.DataFrame(kw.items(), columns=["关键词", "数量"]).sort_values("数量", ascending=False),
                width="stretch", hide_index=True,
            )

        with col_right:
            st.subheader("📋 推文评分明细")
            for e in entries:
                score = e.get("score", "neutral")
                color = SCORE_COLORS.get(score, "#6b7280")
                emoji = SCORE_EMOJI.get(score, "")
                conf = "⭐" * e.get("confidence", 1) + "☆" * (5 - e.get("confidence", 1))
                st.markdown(f"""
                <div class="sentiment-card" style="border-left-color:{color}">
                  <div class="meta-row">{emoji} <strong>{e.get("account", "?")}</strong> · 置信 {conf}
                  &nbsp;|&nbsp; {e.get("keyword", "")} &nbsp;|&nbsp; {(e.get("created_at", "") or "")[:10]}</div>
                  <div class="tweet-body">{e.get("tweet_text", "")}</div>
                </div>
                """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  Page: Watchlist 跟庄
# ═══════════════════════════════════════════════════════════════════
def page_watchlist() -> None:
    st.title("👀 Watchlist 跟庄")
    ts = latest_quote_ts()
    snapshots = load_quote_snapshots()
    if not snapshots:
        st.info("还没有 watchlist 快照。运行 scripts/fetch-tvscreener-watchlist.py --save-db")
        return
    if ts:
        st.caption(f"最新快照: **{ts}**（{_staleness(ts)}）· 来源 tvscreener")

    df = pd.DataFrame(snapshots)
    df["信号"] = df.apply(lambda r: _signal_tags(r), axis=1)
    if {"close", "sma200"}.issubset(df.columns):
        df["SMA200 距离%"] = ((df["close"] - df["sma200"]) / df["sma200"].replace(0, float("nan")) * 100).round(2)
    cols = [c for c in (
        "tv_symbol", "local_name", "asset_class", "close", "change_percent", "volume",
        "rsi", "sma20", "sma50", "sma200", "SMA200 距离%", "recommend_all", "信号",
    ) if c in df.columns]
    st.dataframe(
        df[cols], width="stretch", hide_index=True,
        column_config={
            "close": st.column_config.NumberColumn("收盘", format="$%.2f"),
            "change_percent": st.column_config.NumberColumn("涨跌%", format="%.2f%%"),
            "volume": st.column_config.NumberColumn("成交量", format="%,d"),
            "rsi": st.column_config.NumberColumn("RSI", format="%.1f"),
            "sma20": st.column_config.NumberColumn("SMA20", format="$%.2f"),
            "sma50": st.column_config.NumberColumn("SMA50", format="$%.2f"),
            "sma200": st.column_config.NumberColumn("SMA200", format="$%.2f"),
            "SMA200 距离%": st.column_config.NumberColumn("SMA200 距离%", format="%.2f%%"),
            "recommend_all": st.column_config.NumberColumn("评分", format="%.2f"),
        },
    )

    st.subheader("涨跌幅")
    df_chg = df.dropna(subset=["change_percent"]).sort_values("change_percent", ascending=False)
    if not df_chg.empty:
        col1, col2 = st.columns(2)
        top = df_chg.head(3)[["local_name", "tv_symbol", "change_percent"]]
        bottom = df_chg.tail(3).iloc[::-1][["local_name", "tv_symbol", "change_percent"]]
        col1.markdown("**涨幅榜**")
        col1.dataframe(top, width="stretch", hide_index=True)
        col2.markdown("**跌幅榜**")
        col2.dataframe(bottom, width="stretch", hide_index=True)
        chart = df_chg.set_index(df_chg["local_name"].fillna(df_chg["tv_symbol"]))["change_percent"]
        st.bar_chart(chart, height=240)

    alerts = df[df["信号"].str.contains("超买|超卖")]
    if not alerts.empty:
        st.subheader("⚠️ RSI 极端提示")
        st.dataframe(
            alerts[["local_name", "tv_symbol", "rsi", "信号"]],
            width="stretch", hide_index=True,
        )
    else:
        st.caption("当前无 RSI 极端（>70 超买 / <30 超卖）标的")


# ═══════════════════════════════════════════════════════════════════
#  Page: 运行状态
# ═══════════════════════════════════════════════════════════════════
@_frag(run_every=60)
def _status_panel() -> None:
    st.subheader("服务健康")
    st.table(pd.DataFrame(_service_checks() + _launchd_rows()))

    st.subheader("数据新鲜度")
    fresh = []
    qts = latest_quote_ts()
    fresh.append({"数据": "Watchlist 快照", "时间": qts or "无", "距今": _staleness(qts) if qts else "—"})
    s = load_sentiment_latest()
    sdate = s.get("date") if s else None
    fresh.append({"数据": "情绪扫描", "时间": sdate or "无", "距今": _staleness(sdate) if sdate else "—"})
    live = load_live_state()
    snap = (live or {}).get("last_snapshot") or {}
    lts = max((v.get("ts", "") for v in snap.values()), default="")
    fresh.append({"数据": "实时扫描", "时间": lts or "无", "距今": _staleness(lts) if lts else "—"})
    newest_bt = max(RESULTS_DIR.glob("backtest_*.json"), key=lambda p: p.stat().st_mtime, default=None)
    if newest_bt:
        fresh.append({
            "数据": "最新回测",
            "时间": datetime.fromtimestamp(newest_bt.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "距今": _staleness(datetime.fromtimestamp(newest_bt.stat().st_mtime).isoformat()),
        })
    st.table(pd.DataFrame(fresh))

    runs = _runs_count()
    st.caption(f"SQLite runs 表: {runs} 条回测记录" if runs >= 0 else "SQLite 不可用")

    st.subheader("📁 results/ 文件")
    files = sorted(RESULTS_DIR.glob("*"), reverse=True)[:30]
    file_rows = []
    for r in files:
        if r.is_file():
            file_rows.append({
                "文件": r.name,
                "大小": f"{r.stat().st_size:,} B",
                "修改时间": datetime.fromtimestamp(r.stat().st_mtime).strftime("%m-%d %H:%M"),
            })
    st.dataframe(pd.DataFrame(file_rows), width="stretch", hide_index=True)


def page_status() -> None:
    st.title("🏠 运行状态")
    _status_panel()
    st.caption(f"WhaleTrail · {date.today()} · 面板每 60s 自动刷新")


# ═══════════════════════════════════════════════════════════════════
#  Route
# ═══════════════════════════════════════════════════════════════════
st.sidebar.title("🐋 WhaleTrail")
st.sidebar.caption(f"Mac mini · {date.today()}")
PAGES = {
    "📊 总览": page_overview,
    "📈 回测结果": page_backtest,
    "🔴 实时信号": page_live,
    "🐋 情绪监控": page_sentiment,
    "👀 Watchlist": page_watchlist,
    "🏠 运行状态": page_status,
}
page = st.sidebar.radio("导航", list(PAGES), label_visibility="collapsed")
if st.sidebar.button("🔄 立即刷新", width="stretch"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("总览 / 实时 / 状态页每 60s 自动刷新")
PAGES[page]()
