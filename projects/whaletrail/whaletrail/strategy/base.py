"""Strategy ABC — the base class every strategy must extend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from whaletrail.engine.broker import Order, OrderSide, OrderType


class Strategy(ABC):
    """Abstract base class for all trading strategies.

    Subclasses must implement ``on_bar``.  Helper methods ``buy``, ``sell``,
    and ``order_target_percent`` generate ``Order`` objects that accumulate in
    ``pending_orders`` — the backtester consumes and clears them each bar cycle.

    Parameters
    ----------
    name : str
        Human-readable strategy name (used for logging and storage).
    """

    def __init__(self, name: str) -> None:
        self.name = name

        # Injected by the backtester before the run starts.
        self.broker = None   # Broker
        self.account = None  # Account
        self.current_prices: dict[str, float] = {}

        # Accumulated orders for the *current* bar; cleared by the engine.
        self.pending_orders: list[Order] = []

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        """Called once before backtest starts."""

    @abstractmethod
    def on_bar(self, symbol: str, bar: dict) -> None:
        """Called once per symbol per bar.

        Parameters
        ----------
        symbol : str
            The symbol that produced this bar (e.g. ``"600519.SH"``).
        bar : dict
            Dictionary with keys ``open``, ``high``, ``low``, ``close``,
            ``volume``, and optionally ``date``.
        """
        ...

    def on_finish(self) -> None:
        """Called once after backtest finishes."""

    # ------------------------------------------------------------------
    # Order helpers
    # ------------------------------------------------------------------

    def buy(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        percent: Optional[float] = None,
    ) -> None:
        """Submit a market **buy** order.

        Parameters
        ----------
        symbol : str
        quantity : float, optional
            Absolute number of shares/units.
        percent : float, optional
            Fraction of current portfolio equity to allocate (0.0–1.0).
        """
        qty = self._resolve_quantity(symbol, quantity, percent)
        if qty is not None and qty > 0:
            self.pending_orders.append(
                Order(symbol=symbol, side=OrderSide.BUY, quantity=float(qty))
            )

    def sell(
        self,
        symbol: str,
        quantity: Optional[float] = None,
        percent: Optional[float] = None,
    ) -> None:
        """Submit a market **sell** order.

        Parameters
        ----------
        symbol : str
        quantity : float, optional
            Absolute number of shares/units.
        percent : float, optional
            Fraction of current position to liquidate (0.0–1.0).
        """
        if percent is not None:
            pos = self.account.positions.get(symbol) if self.account else None
            if pos is None or pos.quantity <= 0:
                return
            quantity = abs(pos.quantity) * percent

        qty = self._resolve_quantity(symbol, quantity, None)
        if qty is not None and qty > 0:
            self.pending_orders.append(
                Order(symbol=symbol, side=OrderSide.SELL, quantity=float(qty))
            )

    def order_target_percent(self, symbol: str, target_percent: float) -> None:
        """Adjust position so *symbol* represents ``target_percent`` of
        portfolio equity.

        Parameters
        ----------
        symbol : str
        target_percent : float
            Desired portfolio weight (0.0–1.0).
        """
        if self.account is None:
            return

        equity = self.account.total_equity(self.current_prices)
        current_pos = self.account.positions.get(symbol)
        current_qty = current_pos.quantity if current_pos else 0.0

        price = self.get_price(symbol)
        if price is None or price <= 0:
            return

        target_value = equity * target_percent
        target_qty = target_value / price

        delta = target_qty - current_qty

        if abs(delta) < 1e-8:
            return

        if delta > 0:
            self.buy(symbol, quantity=delta)
        else:
            self.sell(symbol, quantity=abs(delta))

    def get_price(self, symbol: str) -> Optional[float]:
        """Return the latest known close price for *symbol*."""
        return self.current_prices.get(symbol)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_quantity(
        self,
        symbol: str,
        quantity: Optional[float],
        percent: Optional[float],
    ) -> Optional[float]:
        """Compute absolute quantity from *quantity* or *percent*."""
        if percent is not None:
            if self.account is None:
                return None
            if not 0.0 <= percent <= 1.0:
                raise ValueError("percent must be in [0.0, 1.0]")
            equity = self.account.total_equity(self.current_prices)
            price = self.get_price(symbol)
            if price is None or price <= 0:
                return None
            quantity = (equity * percent) / price

        if quantity is not None and quantity <= 0:
            return None

        return quantity
