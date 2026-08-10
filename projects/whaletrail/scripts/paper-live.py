#!/usr/bin/env python3
"""WhaleTrail Paper Live — multi-strategy scan + Telegram.

Gold-first: GLD runs a strategy panel; SPY is hedge context only.

Usage:
  python scripts/paper-live.py tick
  python scripts/paper-live.py loop --interval 600
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yfinance as yf  # noqa: E402

# ── Config ───────────────────────────────────────────────────────
# Primary: gold multi-strategy panel
# Hedge: SPY context (fewer strategies)
SCAN_JOBS = [
    {
        "symbol": "GLD",
        "label": "🥇 黄金",
        "role": "primary",
        "strategies": [
            "gold_sma",
            "gold_sma_v2",
            "bollinger",
            "momentum",
            "turtle",
        ],
    },
    {
        "symbol": "SPY",
        "label": "📊 标普",
        "role": "hedge",
        "strategies": ["ma_cross", "momentum"],
    },
]

STATE_FILE = ROOT / "results" / "paper_live_state.json"
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "5102138680")
PROXY = os.environ.get("HTTPS_PROXY", "http://127.0.0.1:7890")

os.environ.setdefault("HTTPS_PROXY", PROXY)
os.environ.setdefault("HTTP_PROXY", PROXY)


# ── Data ─────────────────────────────────────────────────────────
def fetch_latest(
    symbol: str, interval: str = "5m", lookback_days: int = 10
) -> Any:
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    try:
        df = yf.download(
            symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        print(f"  ⚠️ download error {symbol}: {e}")
        return None
    if df is None or getattr(df, "empty", True):
        return None
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            return None
    return df


def series(df: Any, col: str) -> list[float]:
    return [float(x) for x in df[col].dropna().tolist()]


# ── Indicators ───────────────────────────────────────────────────
def sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / period


def cross_signal(
    closes: list[float], fast: int, slow: int
) -> Optional[str]:
    if len(closes) < slow + 1:
        return None
    f0, s0 = sma(closes, fast), sma(closes, slow)
    f1, s1 = sma(closes[:-1], fast), sma(closes[:-1], slow)
    if None in (f0, s0, f1, s1):
        return None
    if f1 <= s1 and f0 > s0:
        return "BUY"
    if f1 >= s1 and f0 < s0:
        return "SELL"
    return None


# ── Strategy signal functions ────────────────────────────────────
def sig_gold_sma(closes, highs, lows, state, symbol) -> Optional[str]:
    return cross_signal(closes, 20, 50)


def sig_ma_cross(closes, highs, lows, state, symbol) -> Optional[str]:
    return cross_signal(closes, 10, 30)


def sig_gold_sma_v2(closes, highs, lows, state, symbol) -> Optional[str]:
    """SMA20/50 + SMA200 trend filter + ATR trailing stop exit."""
    if len(closes) < 51:
        return None
    c = closes[-1]
    a = atr(highs, lows, closes, 14) or 0
    stops = state.setdefault("atr_stops", {})

    # Exit via stop if we think long
    pos = state.get("positions", {}).get(symbol)
    holding = pos is not None and pos.get("side") == "LONG"
    stop = stops.get(symbol)
    if holding and stop is not None and c < stop:
        stops.pop(symbol, None)
        return "SELL"

    base = cross_signal(closes, 20, 50)
    sma200 = sma(closes, min(200, len(closes))) if len(closes) >= 50 else None

    if base == "BUY":
        if sma200 is not None and c < sma200:
            return None  # trend filter blocks
        if a > 0:
            stops[symbol] = c - 2.0 * a
        return "BUY"
    if base == "SELL":
        stops.pop(symbol, None)
        return "SELL"

    # Trail stop upward while long
    if holding and a > 0 and stop is not None:
        new_stop = c - 2.0 * a
        if new_stop > stop:
            stops[symbol] = new_stop
    return None


def sig_bollinger(closes, highs, lows, state, symbol) -> Optional[str]:
    period, k = 20, 2.0
    if len(closes) < period + 1:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    std = var ** 0.5
    upper, lower = mean + k * std, mean - k * std
    c, prev = closes[-1], closes[-2]
    pos = state.get("positions", {}).get(f"{symbol}_bb")
    holding = pos is not None

    if prev <= upper and c > upper and not holding:
        return "BUY"
    if prev >= lower and c < lower and holding:
        return "SELL"
    # also exit on mean reversion mid-band after long
    if holding and prev >= mean and c < mean:
        return "SELL"
    return None


def sig_momentum(closes, highs, lows, state, symbol) -> Optional[str]:
    period = 20
    if len(closes) < period + 1:
        return None
    mom = (closes[-1] - closes[-period]) / closes[-period]
    mom_prev = (closes[-2] - closes[-period - 1]) / closes[-period - 1]
    if mom_prev <= 0 and mom > 0:
        return "BUY"
    if mom_prev >= 0 and mom < 0:
        return "SELL"
    return None


def sig_turtle(closes, highs, lows, state, symbol) -> Optional[str]:
    entry_n, exit_n = 20, 10
    if len(highs) < entry_n + 1 or len(lows) < exit_n + 1:
        return None
    c = closes[-1]
    entry_high = max(highs[-entry_n - 1 : -1])  # exclude current bar
    exit_low = min(lows[-exit_n - 1 : -1])
    pos = state.get("positions", {}).get(f"{symbol}_turtle")
    holding = pos is not None

    if c > entry_high and not holding:
        return "BUY"
    if c < exit_low and holding:
        return "SELL"
    return None


SIGNAL_FNS = {
    "gold_sma": sig_gold_sma,
    "gold_sma_v2": sig_gold_sma_v2,
    "ma_cross": sig_ma_cross,
    "bollinger": sig_bollinger,
    "momentum": sig_momentum,
    "turtle": sig_turtle,
}


# ── State / Telegram ─────────────────────────────────────────────
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"positions": {}, "last_signals": {}, "last_snapshot": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, default=str, indent=2))


def send_telegram(text: str) -> bool:
    if not TG_TOKEN:
        print("  ⚠️ TG_BOT_TOKEN not set")
        return False
    import urllib.request

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = json.dumps(
        {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    ).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as e:
        print(f"  ⚠️ Telegram: {e}")
        return False


def update_pos_after_signal(state: dict, key: str, signal: str, price: float) -> None:
    if signal == "BUY":
        state.setdefault("positions", {})[key] = {
            "side": "LONG",
            "entry_price": price,
            "entry_date": date.today().isoformat(),
        }
    else:
        state.setdefault("positions", {}).pop(key, None)


# ── Scan ─────────────────────────────────────────────────────────
def tick() -> None:
    state = load_state()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    day = date.today().isoformat()
    all_lines: list[str] = []
    gold_votes: list[str] = []

    for job in SCAN_JOBS:
        symbol = job["symbol"]
        label = job["label"]
        print(f"\n[{now}] {label} {symbol}")

        df = fetch_latest(symbol)
        if df is None:
            print("  ⚠️ no data")
            continue

        closes = series(df, "close")
        highs = series(df, "high")
        lows = series(df, "low")
        if not closes:
            print("  ⚠️ empty closes")
            continue
        price = closes[-1]
        print(f"  price ${price:.2f}  bars={len(closes)}")

        votes: dict[str, str] = {}
        for name in job["strategies"]:
            fn = SIGNAL_FNS.get(name)
            if not fn:
                continue
            try:
                sig = fn(closes, highs, lows, state, symbol)
            except Exception as e:
                print(f"  ⚠️ {name}: {e}")
                sig = None
            if sig is None:
                print(f"  · {name}: —")
                continue
            print(f"  · {name}: {sig}")
            votes[name] = sig

            # Dedup push per strategy/day
            last_key = f"{symbol}|{name}|{sig}"
            if state.get("last_signals", {}).get(last_key) == day:
                continue

            emoji = "🟢" if sig == "BUY" else "🔴"
            msg = (
                f"{emoji} *{label} {symbol}* `{name}` → *{sig}*\n"
                f"价格 ${price:.2f}\n"
                f"{now} · WhaleTrail Live"
            )
            if send_telegram(msg):
                state.setdefault("last_signals", {})[last_key] = day
                # position keys for strategies that track holding
                pos_key = symbol if name in ("gold_sma", "gold_sma_v2", "ma_cross", "momentum") else f"{symbol}_{name[:2]}"
                if name == "bollinger":
                    pos_key = f"{symbol}_bb"
                elif name == "turtle":
                    pos_key = f"{symbol}_turtle"
                update_pos_after_signal(state, pos_key, sig, price)

        if job["role"] == "primary" and votes:
            buys = sum(1 for v in votes.values() if v == "BUY")
            sells = sum(1 for v in votes.values() if v == "SELL")
            n = len(votes)
            consensus = "BUY" if buys > sells and buys >= 2 else (
                "SELL" if sells > buys and sells >= 2 else "MIXED"
            )
            gold_votes = [f"{k}:{v}" for k, v in votes.items()]
            snap_key = f"{symbol}|consensus|{consensus}"
            if consensus != "MIXED" and state.get("last_signals", {}).get(snap_key) != day:
                body = (
                    f"📡 *GLD 策略面板共识 → {consensus}*\n"
                    f"价格 ${price:.2f} | 票数 BUY {buys}/{n} SELL {sells}/{n}\n"
                    f"{', '.join(gold_votes)}\n"
                    f"{now}"
                )
                if send_telegram(body):
                    state.setdefault("last_signals", {})[snap_key] = day
            all_lines.append(
                f"{symbol} ${price:.2f} consensus={consensus} {gold_votes}"
            )
        elif votes:
            all_lines.append(f"{symbol} ${price:.2f} {votes}")

        state.setdefault("last_snapshot", {})[symbol] = {
            "price": price,
            "votes": votes,
            "ts": now,
        }

    save_state(state)
    if all_lines:
        print("\n=== snapshot ===")
        for line in all_lines:
            print(line)


def loop(interval: int = 600) -> None:
    n_strat = sum(len(j["strategies"]) for j in SCAN_JOBS)
    print(
        f"🔄 Paper Live multi-strategy | interval={interval}s | "
        f"jobs={len(SCAN_JOBS)} strategies={n_strat}"
    )
    print(f"   Telegram: {'✅' if TG_TOKEN else '❌ set TG_BOT_TOKEN'}")
    while True:
        try:
            tick()
        except Exception as e:
            print(f"  ⚠️ scan error: {e}")
        print(f"\n⏳ next in {interval}s …")
        time.sleep(interval)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    sp.add_parser("tick")
    lp = sp.add_parser("loop")
    lp.add_argument("--interval", type=int, default=600)
    args = p.parse_args()
    if args.cmd == "loop":
        loop(args.interval)
    else:
        tick()
