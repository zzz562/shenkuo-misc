#!/usr/bin/env python3
"""WhaleTrail Dashboard — 回测 + 情绪监控 双页看板."""
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

st.set_page_config(page_title="WhaleTrail", layout="wide", page_icon="🐋")
ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Sidebar navigation ───────────────────────────────────────────
st.sidebar.title("🐋 WhaleTrail")
page = st.sidebar.radio("导航", ["📈 回测结果", "🐋 情绪监控", "🏠 运行状态"])


# ═══════════════════════════════════════════════════════════════════
#  Page 1: Backtest
# ═══════════════════════════════════════════════════════════════════
def page_backtest() -> None:
    st.title("📈 回测结果")
    files = sorted(RESULTS_DIR.glob("backtest_*.json"), reverse=True)
    if not files:
        st.warning("还没有回测结果，跑一次 backtest 吧")
        return

    selected = st.sidebar.selectbox("选择结果", [f.name for f in files])
    with open(RESULTS_DIR / selected) as f:
        data = json.load(f)

    fe = data.get("final_equity", 0)
    tr = data.get("total_return", 0) * 100
    tc = data.get("total_commission", 0)
    nt = len(data.get("trades", []))
    strategy = data.get("strategy", "?")
    symbol = data.get("symbol", "?")

    cols = st.columns(5)
    cols[0].metric("最终权益", f"${fe:,.0f}")
    cols[1].metric("收益率", f"{tr:.2f}%")
    cols[2].metric("交易次数", nt)
    cols[3].metric("手续费", f"${tc:.2f}")
    cols[4].metric("标的", symbol)
    st.caption(f"策略: **{strategy}** | {data.get('start','?')} → {data.get('end','?')}")

    equity = data.get("equity_curve", [])
    if equity:
        st.subheader("📈 权益曲线")
        df_eq = pd.DataFrame(equity)
        df_eq["date"] = pd.to_datetime(df_eq["date"]).dt.date
        st.line_chart(df_eq.set_index("date")["equity"], use_container_width=True)

    trades = data.get("trades", [])
    if trades:
        st.subheader("📋 交易记录")
        df_tr = pd.DataFrame(trades)
        st.dataframe(df_tr, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════
#  Page 2: Sentiment
# ═══════════════════════════════════════════════════════════════════
def _load_latest_sentiment() -> Optional[dict]:
    f = RESULTS_DIR / "sentiment_latest.json"
    if f.exists():
        return json.loads(f.read_text())
    return None


def _load_sentiment_history() -> list[dict]:
    """Load all daily sentiment files, sorted by date."""
    files = sorted(RESULTS_DIR.glob("sentiment_20*.json"))
    history = []
    for f in files:
        if f.name == "sentiment_latest.json":
            continue
        try:
            d = json.loads(f.read_text())
            history.append(d)
        except Exception:
            pass
    return history


def page_sentiment() -> None:
    st.title("🐋 情绪监控 · Gold Sentiment Index")
    latest = _load_latest_sentiment()
    history = _load_sentiment_history()

    if latest is None:
        st.warning("还没有情绪数据，等 cron 跑第一次（每天 09:00）")
        return

    # ── GSI gauge ──────────────────────────────────────────────
    gsi = latest.get("gold_sentiment_index", 0)
    bullish = latest.get("bullish_count", 0)
    bearish = latest.get("bearish_count", 0)
    neutral = latest.get("neutral_count", 0)
    total = latest.get("total_scored", 0)
    date_str = latest.get("date", "?")

    label = "🟢 看多" if gsi > 0.15 else ("🔴 看空" if gsi < -0.15 else "🟡 中性")
    cols = st.columns(5)
    cols[0].metric("GSI", f"{gsi:+.3f}", label)
    cols[1].metric("看多", bullish)
    cols[2].metric("看空", bearish)
    cols[3].metric("中性", neutral)
    cols[4].metric("总评分", f"{total} 条")
    st.caption(f"数据日期: {date_str} | 来源: 18 位黄金 KOL")

    # ── History chart ───────────────────────────────────────────
    if history:
        st.subheader("📊 GSI 历史")
        df_h = pd.DataFrame(history)
        df_h["date"] = pd.to_datetime(df_h["date"])
        df_h = df_h.set_index("date").sort_index()
        chart_data = df_h[["gold_sentiment_index"]].rename(
            columns={"gold_sentiment_index": "GSI"}
        )
        st.line_chart(chart_data, use_container_width=True)

    # ── Recent entries ──────────────────────────────────────────
    entries = latest.get("entries", [])
    if entries:
        st.subheader("📋 最近评分")
        rows = []
        for e in entries:
            rows.append({
                "账号": e.get("account", "?"),
                "评分": e.get("score", "?"),
                "置信度": e.get("confidence", "?"),
                "关键词": e.get("keyword", "?"),
                "推文": (e.get("tweet_text", "") or "")[:80] + "…",
                "时间": (e.get("created_at", "") or "")[:10],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── GSI distribution bars ───────────────────────────────────
    if total > 0:
        st.subheader("📊 情绪分布")
        dist_df = pd.DataFrame({
            "方向": ["看多 🟢", "看空 🔴", "中性 🟡"],
            "数量": [bullish, bearish, neutral],
        })
        st.bar_chart(dist_df.set_index("方向"), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
#  Page 3: Status
# ═══════════════════════════════════════════════════════════════════
def page_status() -> None:
    st.title("🏠 运行状态")
    import subprocess

    services = {
        "OpenClaw Gateway": 18789,
        "Streamlit Dashboard": 8766,
        "Ollama": 11434,
    }
    rows = []
    for name, port in services.items():
        try:
            import urllib.request
            url = f"http://127.0.0.1:{port}/health" if port == 18789 else f"http://127.0.0.1:{port}"
            with urllib.request.urlopen(url, timeout=3) as resp:
                rows.append({"服务": name, "端口": port, "状态": "✅" if resp.status < 400 else "⚠️"})
        except Exception:
            rows.append({"服务": name, "端口": port, "状态": "❌"})

    # Launchd services
    try:
        out = subprocess.check_output(["launchctl", "list"], text=True, timeout=5)
        for label in ["whaletrail", "ollama", "openclaw"]:
            if label in out:
                pid_line = [l for l in out.split("\n") if label in l]
                if pid_line:
                    rows.append({"服务": f"launchd: {label}", "端口": "-", "状态": "✅"})
    except Exception:
        pass

    st.table(pd.DataFrame(rows))

    # Recent results files
    st.subheader("📁 数据文件")
    results = sorted(RESULTS_DIR.glob("*"), reverse=True)[:20]
    file_rows = [{"文件": r.name, "大小": f"{r.stat().st_size:,} B",
                  "时间": datetime.fromtimestamp(r.stat().st_mtime).strftime("%m-%d %H:%M")}
                 for r in results if r.is_file()]
    st.dataframe(pd.DataFrame(file_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.caption(f"WhaleTrail Dashboard | {date.today()}")


# ── Route ────────────────────────────────────────────────────────
if page == "📈 回测结果":
    page_backtest()
elif page == "🐋 情绪监控":
    page_sentiment()
else:
    page_status()
