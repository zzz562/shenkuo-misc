#!/usr/bin/env python3
"""WhaleTrail Paper Live — multi-strategy scan + Telegram.

Gold-first: GLD runs a strategy panel; SPY is hedge context only.
Scans are gated on NYSE regular hours (whaletrail/engine/session.py), so
weekends/holidays/off-hours never produce signals or paper trades.

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
        "market": "us",
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
        "market": "us",
        "strategies": ["ma_cross", "momentum"],
    },
]

STATE_FILE = ROOT / "results" / "paper_live_state.json"
TG_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "5102138680")
# Proxy config: WT_PROXY_URL → HTTPS_PROXY → default. See docs/ENVIRONMENT.md.
PROXY = os.environ.get("WT_PROXY_URL") or os.environ.get("HTTPS_PROXY") or "http://127.0.0.1:7890"

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


# ── Signal dispatch (single source: strategy registry) ──────────
from whaletrail.engine.session import US_TZ, us_session  # noqa: E402
from whaletrail.strategy.registry import _build_signal_registry  # noqa: E402

SIGNAL_FNS = _build_signal_registry()


def bar_is_fresh(df: Any) -> bool:
    """True if the last bar belongs to today in the market timezone.

    Guards against holidays and stale data: yfinance returns the previous
    session's bars when the market is closed, and a signal computed on them
    would be a paper trade on a non-trading day.
    """
    last = df.index[-1]
    if last.tzinfo is None:
        last_date = last.date()
    else:
        last_date = last.astimezone(US_TZ).date()
    return last_date == datetime.now(US_TZ).date()


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
def tick() -> Optional[str]:
    """Run one scan pass; return a skip note when every job was skipped
    (used by loop() to avoid repeating the same message)."""
    state = load_state()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    day = date.today().isoformat()
    all_lines: list[str] = []
    gold_votes: list[str] = []
    skip_reasons: list[str] = []
    no_data = 0

    for job in SCAN_JOBS:
        symbol = job["symbol"]
        label = job["label"]
        market = job.get("market", "us")
        if market == "us" and not us_session():
            skip_reasons.append("session")
            continue
        df = fetch_latest(symbol)
        if df is None:
            no_data += 1
            print(f"\n[{now}] {label} {symbol}")
            print("  ⚠️ no data")
            continue
        if not bar_is_fresh(df):
            skip_reasons.append("stale")
            continue
        print(f"\n[{now}] {label} {symbol}")

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

    n_jobs = len(SCAN_JOBS)
    if len(skip_reasons) == n_jobs:
        if skip_reasons and all(r == "stale" for r in skip_reasons):
            return "⏸ 无今日 K 线（节假日或数据未更新），跳过本次扫描"
        markets = sorted({job.get("market", "us") for job in SCAN_JOBS})
        return f"⏸ 非交易时段（{'/'.join(markets)}），跳过本次扫描"
    if no_data == n_jobs:
        return "⏸ 数据拉取失败，跳过本次扫描"
    return None


_last_skip_note: Optional[str] = None


def loop(interval: int = 600) -> None:
    global _last_skip_note
    n_strat = sum(len(j["strategies"]) for j in SCAN_JOBS)
    print(
        f"🔄 Paper Live multi-strategy | interval={interval}s | "
        f"jobs={len(SCAN_JOBS)} strategies={n_strat}"
    )
    print(f"   Telegram: {'✅' if TG_TOKEN else '❌ set TG_BOT_TOKEN'}")
    print("   Sessions: 美股 Mon–Fri 09:30–16:00 ET（周末/节假日自动跳过）")
    while True:
        try:
            note = tick()
            if note is not None:
                if note != _last_skip_note:
                    print(note)
                    _last_skip_note = note
            else:
                _last_skip_note = None
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
        note = tick()
        if note:
            print(note)
