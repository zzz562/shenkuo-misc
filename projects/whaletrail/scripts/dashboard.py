#!/usr/bin/env python3
"""WhaleTrail Dashboard — Streamlit app for viewing backtest results."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

st.set_page_config(page_title="WhaleTrail Dashboard", layout="wide")
st.title("🐋 WhaleTrail Dashboard")

# --- Load results ---
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
if not RESULTS_DIR.exists():
    st.error("No results directory found")
    sys.exit(1)

files = sorted(RESULTS_DIR.glob("backtest_*.json"), reverse=True)
if not files:
    st.warning("No backtest results yet. Run a backtest first!")
    sys.exit(0)

# --- Sidebar ---
file_names = [f.name for f in files]
selected = st.sidebar.selectbox("Select Result", file_names)

with open(RESULTS_DIR / selected) as f:
    data = json.load(f)

# --- Metrics row ---
fe = data.get("final_equity", 0)
tr = data.get("total_return", 0) * 100
tc = data.get("total_commission", 0)
nt = len(data.get("trades", []))
strategy = data.get("strategy", "?")
symbol = data.get("symbol", "?")
start = data.get("start", "?")
end = data.get("end", "?")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Final Equity", f"${fe:,.0f}")
col2.metric("Return", f"{tr:.2f}%")
col3.metric("Trades", nt)
col4.metric("Commission", f"${tc:.2f}")
col5.metric("Symbol", symbol)

st.caption(f"Strategy: **{strategy}** | Period: {start} → {end}")

# --- Equity Curve ---
st.subheader("📈 Equity Curve")
equity = data.get("equity_curve", [])
if equity:
    df_eq = pd.DataFrame(equity)
    df_eq["date"] = pd.to_datetime(df_eq["date"])
    df_eq = df_eq.set_index("date")

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df_eq.index, df_eq["equity"], color="#1f77b4", linewidth=1.5)
    ax.fill_between(df_eq.index, 100000, df_eq["equity"],
                    where=(df_eq["equity"] >= 100000),
                    color="green", alpha=0.1)
    ax.fill_between(df_eq.index, 100000, df_eq["equity"],
                    where=(df_eq["equity"] < 100000),
                    color="red", alpha=0.1)
    ax.axhline(y=100000, color="gray", linestyle="--", alpha=0.5, label="Initial")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_ylabel("Equity ($)")
    ax.legend()
    st.pyplot(fig)

# --- Trade Table ---
st.subheader("📋 Trade History")
trades = data.get("trades", [])
if trades:
    df_tr = pd.DataFrame(trades)
    df_tr["date"] = pd.to_datetime(df_tr["date"])
    df_tr = df_tr.sort_values("date", ascending=False)
    st.dataframe(
        df_tr.style.format({"price": "${:.2f}", "commission": "${:.2f}", "quantity": "{:.0f}"}),
        use_container_width=True,
    )
else:
    st.info("No trades in this run")

# --- Performance from metrics module ---
st.subheader("📊 Performance Metrics")
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from whaletrail.metrics.performance import calculate_metrics
    ec = [e["equity"] for e in equity]
    tr_list = [
        {
            "date": t["date"],
            "symbol": t["symbol"],
            "side": t["side"],
            "quantity": t["quantity"],
            "price": t["price"],
            "commission": t["commission"],
            "pnl": 0,
        }
        for t in trades
    ]
    m = calculate_metrics(tr_list, ec, 100000.0)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Return", f"{m.get('total_return', 0):.2f}%")
    c2.metric("Sharpe Ratio", f"{m.get('sharpe_ratio', 0):.2f}")
    c3.metric("Max Drawdown", f"{m.get('max_drawdown', 0):.2f}%")
    c4.metric("Win Rate", f"{m.get('win_rate', 0):.1f}%")
except Exception as e:
    st.caption(f"Metrics calculation not available: {e}")

# --- Footer ---
st.divider()
st.caption(f"WhaleTrail Dashboard | Last updated: {date.today()}")
