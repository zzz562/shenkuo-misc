#!/usr/bin/env python3
"""WhaleTrail Paper Live — 分钟级信号扫描 + Telegram 推送.

Usage:
  python scripts/paper-live.py loop --interval 300   # 每 5 分钟扫一次
  python scripts/paper-live.py tick                   # 单次扫描
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yfinance as yf
import pandas as pd

# ── Config ───────────────────────────────────────────────────────
SYMBOLS = [
    {"symbol": "GLD", "strategy": "gold_sma", "label": "🥇 黄金"},
    {"symbol": "SPY", "strategy": "ma_cross", "label": "📊 标普", "fast": 10, "slow": 30},
]
CACHE_DIR = ROOT / "data_cache"
STATE_FILE = ROOT / "results" / "paper_live_state.json"
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "5102138680")
PROXY = os.environ.get("HTTPS_PROXY", "http://127.0.0.1:7890")

os.environ.setdefault("HTTPS_PROXY", PROXY)
os.environ.setdefault("HTTP_PROXY", PROXY)


# ── Data helpers ─────────────────────────────────────────────────
def fetch_latest(symbol: str, interval: str = "5m", lookback_days: int = 5) -> pd.DataFrame:
    """Fetch recent minute bars via yfinance."""
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    df = yf.download(
        symbol, start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval=interval, progress=False, auto_adjust=True,
    )
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    rename = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    return df


# ── Signal logic ─────────────────────────────────────────────────
def sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def check_gold_sma(closes: list[float], fast: int = 20, slow: int = 50) -> Optional[str]:
    """Return 'BUY' / 'SELL' / None based on SMA crossover."""
    if len(closes) < slow + 1:
        return None
    f_curr = sma(closes, fast)
    s_curr = sma(closes, slow)
    f_prev = sma(closes[:-1], fast)
    s_prev = sma(closes[:-1], slow)
    if f_curr is None or s_curr is None or f_prev is None or s_prev is None:
        return None
    if f_prev <= s_prev and f_curr > s_curr:
        return "BUY"
    if f_prev >= s_prev and f_curr < s_curr:
        return "SELL"
    return None


def check_ma_cross(closes: list[float], fast: int = 10, slow: int = 30) -> Optional[str]:
    return check_gold_sma(closes, fast, slow)


# ── State management ─────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"positions": {}, "last_signals": {}, "cache_date": ""}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, default=str, indent=2))


# ── Telegram push ────────────────────────────────────────────────
def send_telegram(text: str) -> bool:
    if not TG_TOKEN:
        print("  ⚠️ TG_BOT_TOKEN not set, skipping push")
        return False
    import urllib.request
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = json.dumps({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"  ⚠️ Telegram push failed: {e}")
        return False


# ── Main scan ────────────────────────────────────────────────────
def tick() -> None:
    state = load_state()
    now = datetime.now().strftime("%H:%M")
    date_str = date.today().isoformat()

    for cfg in SYMBOLS:
        symbol = cfg["symbol"]
        label = cfg["label"]
        print(f"\n[{now}] {label} {symbol} …")

        df = fetch_latest(symbol)
        if df.empty or "close" not in df.columns:
            print(f"  ⚠️ no data")
            continue

        closes = df["close"].dropna().tolist()
        price = closes[-1] if closes else 0
        print(f"  price: ${price:.2f}  bars: {len(closes)}")

        # Determine strategy
        strat = cfg.get("strategy", "gold_sma")
        if strat == "ma_cross":
            signal = check_ma_cross(closes, cfg.get("fast", 10), cfg.get("slow", 30))
        else:
            signal = check_gold_sma(closes)

        if signal is None:
            print(f"  no signal")
            continue

        # Avoid duplicate notifications
        last_key = f"{symbol}_{signal}"
        last_time = state["last_signals"].get(last_key)
        if last_time == date_str:
            print(f"  signal {signal} (already sent today)")
            continue

        # Build message
        emoji = "🟢" if signal == "BUY" else "🔴"
        prev_price = closes[-2] if len(closes) > 1 else price
        chg = (price - prev_price) / prev_price * 100 if prev_price else 0

        msg = (
            f"{emoji} *{label} {symbol} {signal} 信号*\n"
            f"价格: ${price:.2f}  |  日变化: {chg:+.2f}%\n"
            f"时间: {now}  |  WhaleTrail Paper Live"
        )

        print(f"  → {signal}")
        if send_telegram(msg):
            state["last_signals"][last_key] = date_str
            # Update position state
            if signal == "BUY":
                state["positions"][symbol] = {"entry_price": price, "entry_date": date_str}
            else:
                state["positions"].pop(symbol, None)

    save_state(state)


def loop(interval: int = 300) -> None:
    print(f"🔄 Paper Live loop started (interval={interval}s, {len(SYMBOLS)} symbols)")
    print(f"   Push to Telegram: {'✅' if TG_TOKEN else '❌ (set TG_BOT_TOKEN)'}")
    while True:
        try:
            tick()
        except Exception as e:
            print(f"  ⚠️ scan error: {e}")
        print(f"\n⏳ next scan in {interval}s …")
        time.sleep(interval)


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    sp.add_parser("tick")
    lp = sp.add_parser("loop")
    lp.add_argument("--interval", type=int, default=300)
    args = p.parse_args()
    if args.cmd == "loop":
        loop(args.interval)
    else:
        tick()
