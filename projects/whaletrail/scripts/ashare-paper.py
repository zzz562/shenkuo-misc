#!/usr/bin/env python3
"""A-share low-frequency paper loop (tvscreener snapshot accumulation).

Usage:
  python scripts/ashare-paper.py                    # scan all A-share watchlist items
  python scripts/ashare-paper.py --symbol SSE:601899  # single symbol

Data path: tvscreener snapshot → SQLite ``quote_snapshots`` →
``build_daily_history`` → SMA 20/50 cross signal → paper position tracking
(``results/ashare_paper_state.json``).

Runs are gated on A-share trading days (SZSE official calendar via
``whaletrail/data/trading_calendar.py``, covering weekends, holidays and
make-up days) and the 09:30–16:00 CST snapshot window
(``whaletrail/engine/session.py``); out-of-session runs skip without
recording snapshots or firing signals.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from whaletrail.data.history import build_daily_history
from whaletrail.data.trading_calendar import TradingCalendar
from whaletrail.data.tvscreener_source import TVScreenerSource
from whaletrail.data.watchlist import by_tv_symbol, load_watchlist
from whaletrail.engine.session import CN_TZ, ashare_hours
from whaletrail.indicators import cross_signal
from whaletrail.storage.repository import Repository

DB_PATH = ROOT / "results" / "whaletrail.db"
STATE_FILE = ROOT / "results" / "ashare_paper_state.json"
WATCHLIST = ROOT / "config" / "watchlist.yaml"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"positions": {}}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str))


def fetch_and_save(items, repo) -> None:
    source = TVScreenerSource()
    symbols = [item.tv_symbol for item in items]
    snapshots = source.get_quotes(symbols)
    item_by_tv = by_tv_symbol(items)

    rows = []
    for snap in snapshots:
        data = snap.to_dict()
        item = item_by_tv.get(snap.symbol)
        data["tv_symbol"] = snap.symbol
        if item is not None:
            data.update(
                {
                    "local_name": item.name,
                    "yahoo_symbol": item.yahoo_symbol,
                    "asset_class": item.asset_class,
                    "exchange": item.exchange or data.get("exchange"),
                    "tradable": item.tradable,
                }
            )
        rows.append(data)

    if rows:
        repo.save_quote_snapshots(rows)
    print(f"fetched {len(rows)} snapshots")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", help="Single tvscreener symbol, e.g. SSE:601899")
    args = parser.parse_args()

    today = datetime.now(CN_TZ).date()
    if not ashare_hours():
        print(
            f"⏸ 非 A 股交易时段（盘外），跳过 | 当前 "
            f"{datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M')} CST"
        )
        return
    if not TradingCalendar().is_trading_day(today):
        print(f"⏸ 今日非 A 股交易日（周末/节假日），跳过 | {today.isoformat()}")
        return

    items = load_watchlist(WATCHLIST)
    a_items = [i for i in items if i.market == "china" and i.tradable]
    if args.symbol:
        a_items = [i for i in a_items if i.tv_symbol == args.symbol]

    if not a_items:
        print("No A-share watchlist items found.")
        return

    repo = Repository(DB_PATH)
    state = load_state()

    print(f"\n🅰  A股低频 paper  |  {date.today().isoformat()}")
    try:
        fetch_and_save(a_items, repo)
    except Exception as exc:
        print(f"  ⚠️ 快照拉取失败: {exc}（继续用已有历史）")

    print()
    for item in a_items:
        hist = build_daily_history(DB_PATH, item.tv_symbol)
        if hist.empty or len(hist) < 60:
            print(f"{item.name} ({item.tv_symbol}): 历史不足（{len(hist)} 天），跳过")
            continue

        closes = hist["close"].astype(float).dropna().tolist()
        price = closes[-1]
        sig = cross_signal(closes, 20, 50)
        pos = state.get("positions", {}).get(item.tv_symbol)

        if sig == "BUY" and (pos is None or pos.get("side") != "LONG"):
            state.setdefault("positions", {})[item.tv_symbol] = {
                "side": "LONG",
                "entry_price": price,
                "entry_date": date.today().isoformat(),
            }
            print(f"🟢 {item.name} ({item.tv_symbol}) BUY @ {price:.2f}")
        elif sig == "SELL" and pos and pos.get("side") == "LONG":
            pnl_pct = (price / pos["entry_price"] - 1.0) * 100.0
            state["positions"].pop(item.tv_symbol, None)
            print(f"🔴 {item.name} ({item.tv_symbol}) SELL @ {price:.2f}  (paper PnL {pnl_pct:+.2f}%)")
        else:
            if pos and pos.get("side") == "LONG":
                pnl_pct = (price / pos["entry_price"] - 1.0) * 100.0
                status = f"持有  {pnl_pct:+.2f}%"
            else:
                status = "空仓"
            print(f"➖ {item.name} ({item.tv_symbol}) {price:.2f}  {sig or '—'}  {status}")

    repo.close()
    save_state(state)


if __name__ == "__main__":
    main()
