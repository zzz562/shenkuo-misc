"""Backtester — the main event loop.

Orchestrates a bar‑by‑bar backtest: loads data, iterates dates,
feeds bars to the strategy, collects pending orders, matches them
through the broker, and records the equity curve.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

import pandas as pd

from .account import Account
from .broker import Broker
from .types import Order
from .clock import TradingClock
from ..strategy.base import Strategy


# ---------------------------------------------------------------------------
#  Data-source protocol (any object with a get_daily method works)
# ---------------------------------------------------------------------------


class DataSource(Protocol):
    """Structural protocol for data sources."""

    def get_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        ...


# ---------------------------------------------------------------------------
#  Internal records
# ---------------------------------------------------------------------------


@dataclass
class _TradeRecord:
    date: Any  # bar timestamp (pd.Timestamp for intraday, date-like for daily)
    symbol: str
    side: str
    quantity: float
    price: float
    commission: float


@dataclass
class _EquityPoint:
    date: Any  # bar timestamp
    equity: float
    cash: float


# ---------------------------------------------------------------------------
#  Backtester
# ---------------------------------------------------------------------------


class Backtester:
    """Event‑loop backtester.

    Loads all data upfront, then iterates bar‑by‑bar (timeframe‑agnostic:
    daily or intraday), symbol‑by‑symbol calling the strategy and matching
    orders.  Orders placed on bar N fill at bar N+1's open (no look‑ahead).

    Args:
        symbols: List of tickers to backtest.
        strategy: A Strategy instance (on_bar will be called per bar).
        data_source: Object with get_daily(symbol, start, end) -> DataFrame.
        start: First trading date (inclusive).
        end: Last trading date (inclusive).
        initial_cash: Starting cash balance.
    """

    def __init__(
        self,
        symbols: list[str],
        strategy: Strategy,
        data_source: DataSource,
        start: date,
        end: date,
        initial_cash: float = 1_000_000.0,
    ) -> None:
        self.symbols = symbols
        self.strategy = strategy
        self.data_source = data_source
        self.start = start
        self.end = end
        self.initial_cash = initial_cash

        # Internals
        self._account: Account = Account(initial_cash=initial_cash)
        self._broker: Broker = Broker()
        self._data_cache: dict[str, pd.DataFrame] = {}
        self._trades: list[_TradeRecord] = []
        self._equity_curve: list[_EquityPoint] = []

    # ------------------------------------------------------------------
    #  Run
    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Execute the full backtest.

        Returns a dict with keys:
        * ``trades``: list of trade dicts
        * ``equity_curve``: list of (date, equity, cash) dicts
        * ``final_equity``: ending total equity
        * ``total_commission``: cumulative commission paid
        * ``total_return``: (final_equity / initial_cash - 1) as fraction
        """
        self._reset_state()

        # ---- Load all data upfront -----------------------------------
        for symbol in self.symbols:
            df = self.data_source.get_daily(symbol, self.start, self.end)
            if df.empty:
                raise ValueError(
                    f"No data returned for {symbol} from {self.start} to {self.end}"
                )
            if not isinstance(df.index, pd.DatetimeIndex):
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.set_index("date")
                else:
                    raise ValueError(
                        f"DataFrame for {symbol} must have a date index or 'date' column"
                    )
            df = df.sort_index()
            self._data_cache[symbol] = df

        # ---- Align all symbols to a common bar timeline --------------
        timeline = self._build_timeline()
        if not timeline:
            raise ValueError("No bars after aligning all symbols")

        clock = TradingClock(timeline)

        # ---- Wire strategy to broker & account -----------------------
        self.strategy.broker = self._broker
        self.strategy.account = self._account
        self.strategy.on_start()

        # ---- Main loop -----------------------------------------------
        for ts in clock:
            self._process_bar(ts)

        # ---- Teardown ------------------------------------------------
        self.strategy.on_finish()

        return self._build_results()

    # ------------------------------------------------------------------
    #  Internal helpers
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        self._account = Account(initial_cash=self.initial_cash)
        self._broker = Broker()
        self._trades.clear()
        self._equity_curve.clear()
        self._data_cache.clear()
        self.strategy.current_prices = {}
        self.strategy.pending_orders = []

    def _build_timeline(self) -> list[pd.Timestamp]:
        """Union of all symbols' bar timestamps, filtered to [start, end].

        The engine is bar-driven and timeframe-agnostic: for daily data the
        timeline holds one timestamp per session, for intraday data one per
        bar.  The end date is inclusive for the whole day (intraday bars
        timestamped during *end* are kept).
        """
        all_indices = [df.index for df in self._data_cache.values()]
        if not all_indices:
            return []

        common = all_indices[0]
        for idx in all_indices[1:]:
            common = common.union(idx)

        end_exclusive = pd.Timestamp(self.end) + pd.Timedelta(days=1)
        common = common[(common >= pd.Timestamp(self.start)) & (common < end_exclusive)]
        return sorted(common)

    def _process_bar(self, ts: pd.Timestamp) -> None:
        """Process all symbols for a single bar.

        Order of operations (avoids look‑ahead bias):
        1. Match orders queued from the *previous* bar at this bar's open.
        2. Feed this bar to the strategy (new orders go to pending_orders).
        3. Send pending_orders to broker for next-bar execution.
        4. Record end-of-bar equity snapshot.
        """

        # ── Step 1: match previous bar's queued orders against this open ──
        for symbol in self.symbols:
            bar = self._get_bar(symbol, ts)
            if bar is None:
                continue

            fills = self._broker.match_pending_for_symbol(symbol, bar)
            for fill in fills:
                self._account.apply_fill(fill)
                self._trades.append(
                    _TradeRecord(
                        date=ts,
                        symbol=fill.symbol,
                        side="BUY" if fill.quantity > 0 else "SELL",
                        quantity=abs(fill.quantity),
                        price=fill.price,
                        commission=fill.commission,
                    )
                )

        # Day-order expiry: anything not filled at this bar's open dies here.
        self._broker.cancel_unfilled()

        # ── Step 2: feed bars to strategy → new orders go to pending_orders ──
        for symbol in self.symbols:
            bar = self._get_bar(symbol, ts)
            if bar is None:
                continue

            self.strategy.current_prices[symbol] = bar["close"]
            self.strategy.on_bar(symbol, bar)

        # ── Step 3: submit pending_orders to broker for next-bar execution ──
        for order in self.strategy.pending_orders:
            self._broker.place_order(order)
        self.strategy.pending_orders = []

        # ── Step 4: end-of-bar equity snapshot ──
        self._account.mark_prices(self.strategy.current_prices)
        equity = self._account.total_equity(self.strategy.current_prices)
        self._equity_curve.append(
            _EquityPoint(date=ts, equity=equity, cash=self._account.cash)
        )

    def _get_bar(self, symbol: str, ts: pd.Timestamp) -> dict[str, Any] | None:
        """Extract a single bar dict for *symbol* at timestamp *ts*."""
        df = self._data_cache.get(symbol)
        if df is None:
            return None

        if ts not in df.index:
            return None

        row = df.loc[ts]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        return {
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "date": ts,
        }

    def _build_results(self) -> dict[str, Any]:
        """Assemble the results dict."""
        final_equity = (
            self._equity_curve[-1].equity if self._equity_curve else self.initial_cash
        )
        total_return = (final_equity / self.initial_cash) - 1.0

        return {
            "trades": [
                {
                    "date": t.date,
                    "symbol": t.symbol,
                    "side": t.side,
                    "quantity": t.quantity,
                    "price": t.price,
                    "commission": t.commission,
                }
                for t in self._trades
            ],
            "equity_curve": [
                {"date": p.date, "equity": p.equity, "cash": p.cash}
                for p in self._equity_curve
            ],
            "final_equity": final_equity,
            "total_commission": self._account.total_commission,
            "total_return": total_return,
        }

    # ------------------------------------------------------------------
    #  Convenience properties
    # ------------------------------------------------------------------

    @property
    def account(self) -> Account:
        return self._account

    @property
    def broker(self) -> Broker:
        return self._broker
