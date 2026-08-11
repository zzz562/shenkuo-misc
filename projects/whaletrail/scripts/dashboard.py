#!/usr/bin/env python3
"""WhaleTrail Dashboard — 回测 + 情绪监控."""
import json, sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="WhaleTrail", layout="wide", page_icon="🐋")
ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════════
SCORE_COLORS = {"bullish": "#16a34a", "bearish": "#dc2626", "neutral": "#6b7280"}
SCORE_EMOJI = {"bullish": "📈", "bearish": "📉", "neutral": "➖"}

st.markdown("""
<style>
.big-metric { font-size: 2.4rem; font-weight: 700; }
.sentiment-card { border-left: 4px solid #3b82f6; padding: 0.8rem 1rem; margin: 0.3rem 0; border-radius: 6px; background: #f8fafc; }
.tweet-body { font-size: 0.95rem; line-height: 1.5; color: #1e293b; }
.meta-row { color: #64748b; font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🐋 WhaleTrail")
st.sidebar.caption(f"Mac mini · {date.today()}")
page = st.sidebar.radio("", ["📈 回测结果", "🐋 情绪监控", "🏠 运行状态"])


# ═══════════════════════════════════════════════════════════════════
#  Page: 回测结果
# ═══════════════════════════════════════════════════════════════════
def page_backtest() -> None:
    st.title("📈 回测结果")
    files = sorted(RESULTS_DIR.glob("backtest_*.json"), reverse=True)
    if not files:
        st.warning("还没有回测结果")
        return
    selected = st.sidebar.selectbox("选择", [f.name for f in files], label_visibility="collapsed")
    with open(RESULTS_DIR / selected) as f:
        data = json.load(f)

    fe, tr, tc = data.get("final_equity", 0), data.get("total_return", 0) * 100, data.get("total_commission", 0)
    nt = len(data.get("trades", []))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("最终权益", f"${fe:,.0f}")
    c2.metric("收益率", f"{tr:.2f}%", delta=f"{tr:.2f}%")
    c3.metric("交易次数", nt)
    c4.metric("手续费", f"${tc:.2f}")
    c5.metric("标的", data.get("symbol", "?"))
    st.caption(f"策略: **{data.get('strategy','?')}** · {data.get('start','?')} → {data.get('end','?')}")

    equity = data.get("equity_curve", [])
    if equity:
        df_eq = pd.DataFrame(equity)
        df_eq["date"] = pd.to_datetime(df_eq["date"])
        st.subheader("权益曲线")
        st.line_chart(df_eq.set_index("date")["equity"], use_container_width=True)

    trades = data.get("trades", [])
    if trades:
        st.subheader("交易记录")
        st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════
#  Page: 情绪监控
# ═══════════════════════════════════════════════════════════════════
def _load_latest() -> Optional[dict]:
    f = RESULTS_DIR / "sentiment_latest.json"
    return json.loads(f.read_text()) if f.exists() else None

def _load_history() -> list[dict]:
    return [json.loads(f.read_text()) for f in sorted(RESULTS_DIR.glob("sentiment_20*.json"))
            if f.name != "sentiment_latest.json"]

def page_sentiment() -> None:
    st.title("🐋 Gold Sentiment Index")
    latest = _load_latest()
    if not latest:
        st.info("等待首次情绪扫描（每天 09:00 cron）")
        return

    gsi = latest.get("gold_sentiment_index", 0)
    bullish, bearish, neutral = latest.get("bullish_count", 0), latest.get("bearish_count", 0), latest.get("neutral_count", 0)
    total = latest.get("total_scored", 0)
    entries = latest.get("entries", [])

    # ── Hero row ────────────────────────────────────────────────
    tag = "🟢 看多" if gsi > 0.15 else ("🔴 看空" if gsi < -0.15 else "🟡 中性")
    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 2])
    c1.metric("GSI 情绪指数", f"{gsi:+.3f}", tag)
    c2.metric("📈 看多", bullish)
    c3.metric("📉 看空", bearish)
    c4.metric("➖ 中性", neutral)
    c5.metric("📊 扫描", f"{total} 条推文")
    st.caption(f"数据日期: **{latest.get('date', '?')}** · 来源: 18 位黄金 KOL · 每日 09:00 更新")

    # ── History chart (improved) ────────────────────────────────
    history = _load_history()
    if history:
        st.subheader("📊 GSI 历史趋势")
        df_h = pd.DataFrame(history).sort_values("date")
        df_h["date"] = pd.to_datetime(df_h["date"])
        df_h = df_h.set_index("date")

        # Dual chart: GSI line + bar area
        import altair as alt
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

        chart = (bar + bar2 + line).resolve_scale(y="independent")
        st.altair_chart(chart, use_container_width=True)

        # Summary table below chart
        st.caption("每日汇总")
        tbl = source[["date", "GSI", "Bullish", "Bearish", "neutral_count"]].rename(
            columns={"neutral_count": "Neutral"}
        ).tail(10)
        st.dataframe(tbl.set_index("date"), use_container_width=True)

    # ── Distribution + tweet feed ────────────────────────────────
    if entries:
        col_left, col_right = st.columns([1, 2])
        with col_left:
            st.subheader("情绪分布")
            df_dist = pd.DataFrame({"方向": ["📈 看多", "📉 看空", "➖ 中性"], "数量": [bullish, bearish, neutral]})
            st.bar_chart(df_dist.set_index("方向"), use_container_width=True)

            # Per-KOL summary
            kol_stats = {}
            for e in entries:
                acc = e.get("account", "?")
                if acc not in kol_stats:
                    kol_stats[acc] = {"bullish": 0, "bearish": 0, "neutral": 0}
                kol_stats[acc][e.get("score", "neutral")] += 1
            st.caption(f"覆盖 KOL: {len(kol_stats)} 位")

        with col_right:
            st.subheader("📋 推文评分明细")
            for e in entries:
                score = e.get("score", "neutral")
                color = SCORE_COLORS.get(score, "#6b7280")
                emoji = SCORE_EMOJI.get(score, "")
                conf = "⭐" * e.get("confidence", 1) + "☆" * (5 - e.get("confidence", 1))

                st.markdown(f"""
                <div class="sentiment-card" style="border-left-color:{color}">
                  <div class="meta-row">{emoji} <strong>{e.get("account","?")}</strong> · 置信 {conf}
                  &nbsp;|&nbsp; {e.get("keyword","")} &nbsp;|&nbsp; {(e.get("created_at","") or "")[:10]}</div>
                  <div class="tweet-body">{e.get("tweet_text","")}</div>
                </div>
                """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════
#  Page: 运行状态
# ═══════════════════════════════════════════════════════════════════
def page_status() -> None:
    st.title("🏠 运行状态")

    # Services health
    checks = {"OpenClaw Gateway": ("http://127.0.0.1:18789/health", 18789),
              "Dashboard": ("http://127.0.0.1:8766", 8766),
              "Ollama": ("http://127.0.0.1:11434/api/tags", 11434)}
    rows = []
    import urllib.request
    for name, (url, port) in checks.items():
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                rows.append({"服务": name, "端口": port, "状态": "✅" if r.status < 400 else "⚠️"})
        except Exception:
            rows.append({"服务": name, "端口": port, "状态": "❌"})

    # Launchd
    import subprocess
    try:
        out = subprocess.check_output(["launchctl", "list"], text=True, timeout=5)
        for label, display in [("whaletrail", "Paper Live"), ("ollama", "Ollama"), ("openclaw", "OpenClaw")]:
            rows.append({"服务": f"launchd: {display}", "端口": "-",
                         "状态": "✅" if label in out else "❌"})
    except Exception:
        pass

    st.table(pd.DataFrame(rows))

    # File listing
    st.subheader("📁 results/ 文件")
    files = sorted(RESULTS_DIR.glob("*"), reverse=True)[:30]
    file_rows = []
    for r in files:
        if r.is_file():
            file_rows.append({"文件": r.name, "大小": f"{r.stat().st_size:,} B",
                              "修改时间": datetime.fromtimestamp(r.stat().st_mtime).strftime("%m-%d %H:%M")})
    st.dataframe(pd.DataFrame(file_rows), use_container_width=True, hide_index=True)
    st.caption(f"WhaleTrail · {date.today()}")


# ── Route ────────────────────────────────────────────────────────
{"📈 回测结果": page_backtest, "🐋 情绪监控": page_sentiment, "🏠 运行状态": page_status}[page]()
