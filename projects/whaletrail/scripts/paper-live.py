#!/usr/bin/env python3
"""WhaleTrail Paper Live — multi-strategy daily-bar scan + Telegram.

Signals are computed on **completed daily bars** (1d), exactly like the
backtested strategies, and paper fills are recorded at **today's open** —
the same "signal at close N → fill at open N+1" assumption the backtester
uses (`whaletrail/engine/backtester.py`).  A single scan shortly after the
US open (09:30–16:00 ET session gate, `whaletrail/engine/session.py`)
captures everything the daily strategies can produce for the day; running
more often only re-confirms the same signals (dedup is per strategy/day).

Usage:
  python scripts/paper-live.py tick
  python scripts/paper-live.py loop --interval 1800
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

# Daily-bar signal inputs: SMA200 warm-up + slow-window strategies need a
# long history; 420 calendar days ≈ 285+ trading sessions.
DAILY_LOOKBACK_DAYS = 420
MIN_DAILY_BARS = 260
# Reject the series when the last completed bar moves more than this vs the
# prior close — on GLD/SPY that means a split or a corrupt feed, not a trade.
MAX_DAY_MOVE = 0.25

# ── Data ─────────────────────────────────────────────────────────
def fetch_daily(symbol: str, lookback_days: int = DAILY_LOOKBACK_DAYS) -> Any:
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    try:
        df = yf.download(
            symbol,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
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


def validate_daily(df: Any, symbol: str) -> Optional[str]:
    """Data-quality gate.  Returns a rejection reason, or None when clean.

    Signals are only as good as their input: refuse to trade (even paper)
    on bars that fail basic sanity checks.
    """
    if len(df) < MIN_DAILY_BARS:
        return f"only {len(df)} daily bars (< {MIN_DAILY_BARS})"
    closes = df["close"]
    if closes.isna().any():
        return "NaN close in series"
    if (closes <= 0).any():
        return "non-positive close in series"
    last, prev = float(closes.iloc[-1]), float(closes.iloc[-2])
    move = abs(last / prev - 1.0)
    if move > MAX_DAY_MOVE:
        return (
            f"last completed bar moved {move:.1%} vs prior close — "
            "split or corrupt feed?"
        )
    return None


def split_today(df: Any) -> tuple[Any, Optional[float]]:
    """Split off today's (partial) bar.

    Returns (completed_bars_df, today_open).  today_open is None when the
    last bar is not today's — i.e. stale data / holiday.
    """
    last = df.index[-1]
    last_date = last.date() if last.tzinfo is None else last.astimezone(US_TZ).date()
    if last_date != datetime.now(US_TZ).date():
        return df, None
    return df.iloc[:-1], float(df["open"].iloc[-1])


# ── Signal dispatch (single source: strategy registry) ──────────
from whaletrail.engine.session import US_TZ, us_session  # noqa: E402
from whaletrail.strategy.base import position_key  # noqa: E402
from whaletrail.strategy.registry import _build_signal_registry  # noqa: E402

SIGNAL_FNS = _build_signal_registry()


# ── State / Telegram ─────────────────────────────────────────────
def load_state() -> dict:
    state: dict = {"positions": {}, "last_signals": {}, "last_snapshot": {}}
    if STATE_FILE.exists():
        try:
            state.update(json.loads(STATE_FILE.read_text()))
        except Exception:
            pass
    # Migration (2026-08-18): position slots are per (symbol, strategy).
    # Legacy keys ("GLD", "GLD_bb", "GLD_turtle") mixed strategies'
    # bookkeeping and are dropped; atr_stops from that era go with them.
    positions = state.get("positions", {})
    legacy = [k for k in positions if "|" not in k]
    if legacy:
        print(f"  ⚠️ dropping legacy position keys: {sorted(legacy)}")
        for k in legacy:
            positions.pop(k, None)
    stops = state.get("atr_stops", {})
    if any("|" not in k for k in stops):
        print("  ⚠️ dropping legacy atr_stops (rebuilt on next BUY)")
        state["atr_stops"] = {k: v for k, v in stops.items() if "|" in k}
    return state


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


def update_pos_after_signal(
    state: dict, key: str, signal: str, fill_price: float, signal_date: str
) -> None:
    if signal == "BUY":
        state.setdefault("positions", {})[key] = {
            "side": "LONG",
            "entry_price": fill_price,
            "entry_date": date.today().isoformat(),
            "signal_date": signal_date,
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
    skip_reasons: list[str] = []

    # ── Pass 1: fetch + validate ─────────────────────────────────
    prepared: dict[str, dict] = {}
    for job in SCAN_JOBS:
        symbol = job["symbol"]
        if job.get("market", "us") == "us" and not us_session():
            skip_reasons.append("session")
            continue
        df = fetch_daily(symbol)
        if df is None:
            skip_reasons.append("no_data")
            print(f"\n[{now}] {job['label']} {symbol}\n  ⚠️ no data")
            continue
        hist, today_open = split_today(df)
        if today_open is None:
            skip_reasons.append("stale")
            continue
        if today_open <= 0:
            skip_reasons.append("invalid")
            print(f"\n[{now}] {job['label']} {symbol}\n  ⚠️ data rejected: non-positive today's open")
            continue
        problem = validate_daily(hist, symbol)
        if problem is not None:
            skip_reasons.append("invalid")
            print(f"\n[{now}] {job['label']} {symbol}\n  ⚠️ data rejected: {problem}")
            continue
        prepared[symbol] = {"hist": hist, "open": today_open, "job": job}

    # Cross-instrument corruption guard: two different symbols must never
    # print the exact same open and close (observed in a broken feed).
    fps: dict[tuple[float, float], str] = {}
    for symbol, pack in prepared.items():
        fp = (round(pack["open"], 4), round(float(pack["hist"]["close"].iloc[-1]), 4))
        other = fps.get(fp)
        if other is not None:
            print(
                f"  ⚠️ {symbol} and {other} report identical open/close "
                f"{fp} — feed corrupt, skipping both"
            )
            prepared.pop(symbol, None)
            prepared.pop(other, None)
        else:
            fps[fp] = symbol

    # ── Pass 2: signals on completed bars, fills at today's open ──
    for symbol, pack in prepared.items():
        job, hist, exec_open = pack["job"], pack["hist"], pack["open"]
        label = job["label"]
        signal_date = str(hist.index[-1].date() if hasattr(hist.index[-1], "date") else hist.index[-1])

        closes = series(hist, "close")
        highs = series(hist, "high")
        lows = series(hist, "low")
        if not closes:
            print(f"  ⚠️ empty closes for {symbol}")
            continue
        last_close = closes[-1]
        print(
            f"\n[{now}] {label} {symbol}  open ${exec_open:.2f}  "
            f"prev close ${last_close:.2f}  bars={len(closes)}"
        )

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
                f"信号日 {signal_date} 收盘确认 · 按今日开盘价 ${exec_open:.2f} 记账\n"
                f"{now} · WhaleTrail Live (daily)"
            )
            if send_telegram(msg):
                state.setdefault("last_signals", {})[last_key] = day
                update_pos_after_signal(
                    state, position_key(symbol, name), sig, exec_open, signal_date
                )

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
                    f"今日开盘 ${exec_open:.2f} | 票数 BUY {buys}/{n} SELL {sells}/{n}\n"
                    f"{', '.join(gold_votes)}\n"
                    f"{now}"
                )
                if send_telegram(body):
                    state.setdefault("last_signals", {})[snap_key] = day
            all_lines.append(
                f"{symbol} open ${exec_open:.2f} consensus={consensus} {gold_votes}"
            )
        elif votes:
            all_lines.append(f"{symbol} open ${exec_open:.2f} {votes}")

        state.setdefault("last_snapshot", {})[symbol] = {
            # "price" kept for the dashboard's price cards; equals today's open.
            "price": exec_open,
            "open": exec_open,
            "prev_close": last_close,
            "signal_date": signal_date,
            "votes": votes,
            "ts": now,
        }

    save_state(state)
    if all_lines:
        print("\n=== snapshot ===")
        for line in all_lines:
            print(line)

    n_jobs = len(SCAN_JOBS)
    if prepared:
        return None
    if len(skip_reasons) >= n_jobs:
        if skip_reasons and all(r == "stale" for r in skip_reasons):
            return "⏸ 无今日 K 线（节假日或数据未更新），跳过本次扫描"
        markets = sorted({job.get("market", "us") for job in SCAN_JOBS})
        return f"⏸ 非交易时段（{'/'.join(markets)}），跳过本次扫描"
    return "⏸ 无有效数据（拉取失败或质检拦截），跳过本次扫描"


_last_skip_note: Optional[str] = None


def loop(interval: int = 1800) -> None:
    global _last_skip_note
    n_strat = sum(len(j["strategies"]) for j in SCAN_JOBS)
    print(
        f"🔄 Paper Live daily signals | interval={interval}s | "
        f"jobs={len(SCAN_JOBS)} strategies={n_strat}"
    )
    print(f"   Telegram: {'✅' if TG_TOKEN else '❌ set TG_BOT_TOKEN'}")
    print("   Sessions: 美股 Mon–Fri 09:30–16:00 ET（周末/节假日自动跳过）")
    print("   Signals: 已收盘日线 · 按当日开盘价记账（与回测假设一致）")
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
    lp.add_argument("--interval", type=int, default=1800)
    args = p.parse_args()
    if args.cmd == "loop":
        loop(args.interval)
    else:
        note = tick()
        if note:
            print(note)
