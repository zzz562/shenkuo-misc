"""Simulated broker for the WhaleTrail backtesting engine.

Handles order matching, commission calculation, and slippage modelling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class Order:
    """A trading order placed by a strategy.

    Attributes:
        symbol: Ticker symbol.
        side: BUY or SELL.
        quantity: Number of shares (always positive).
        order_type: MARKET or LIMIT.
        limit_price: Required for LIMIT orders; the price threshold.
    """

    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {self.quantity}")
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order requires a limit_price")


@dataclass
class Fill:
    """A completed trade (order fill).

    Attributes:
        symbol: Ticker symbol.
        quantity: Signed quantity (+ for buy, − for sell).
        price: Execution price per share.
        commission: Commission charged for this fill.
    """

    symbol: str
    quantity: float
    price: float
    commission: float = 0.0


@dataclass
class Broker:
    """Simulated broker that matches orders against bar data.

    A‑share defaults:
        commission_rate = 0.0005  (~5 bps, US-style retail)
        min_commission  = 0.0     (no A-share floor)

    Slippage is fixed at 0 (for now).

    Args:
        commission_rate: Fraction of notional (default 5 bps for US/ETF paper).
        min_commission: Floor commission per fill (0 for US-style paper).
    """

    commission_rate: float = 0.0005
    min_commission: float = 0.0
    slippage: float = field(default=0.0, init=False)

    _pending_orders: list[Order] = field(default_factory=list, init=False, repr=False)
    _fills: list[Fill] = field(default_factory=list, init=False, repr=False)

    # ------------------------------------------------------------------
    #  Order intake
    # ------------------------------------------------------------------

    def place_order(self, order: Order) -> None:
        """Accept an order from a strategy for future matching."""
        self._pending_orders.append(order)

    @property
    def pending_orders(self) -> list[Order]:
        """Read-only view of pending (unfilled) orders."""
        return list(self._pending_orders)

    @property
    def fills(self) -> list[Fill]:
        """Read-only view of fills produced so far."""
        return list(self._fills)

    # ------------------------------------------------------------------
    #  Matching
    # ------------------------------------------------------------------

    def match_order(self, order: Order, bar: dict[str, Any]) -> Fill | None:
        """Attempt to match an *order* against the current *bar*.

        *bar* must be a dict (or pd.Series) containing at least
        ``open``, ``high``, ``low``, ``close``.

        Matching rules
        ---------------
        * **Market order**: fills at the bar's open price (avoids look‑ahead).
        * **Limit order**: fills only when the limit price is within the
          bar's high/low range.  Fill price = limit_price (favourable fill
          assumed).
        * Orders are always fully filled (no partial fills yet).

        Returns:
            A Fill if the order was matched, or ``None`` if it cannot be
            filled in this bar.
        """
        # Extract OHLC
        open_p = float(bar["open"])
        high_p = float(bar["high"])
        low_p = float(bar["low"])
        # close is not used for matching but we extract for completeness

        if order.order_type == OrderType.MARKET:
            fill_price = open_p
        elif order.order_type == OrderType.LIMIT:
            assert order.limit_price is not None
            # Buy limit: fills when low <= limit_price (i.e. price traded at or below limit)
            # Sell limit: fills when high >= limit_price (i.e. price traded at or above limit)
            if order.side == OrderSide.BUY and low_p <= order.limit_price:
                fill_price = order.limit_price
            elif order.side == OrderSide.SELL and high_p >= order.limit_price:
                fill_price = order.limit_price
            else:
                return None  # Limit not reached this bar
        else:
            raise ValueError(f"Unknown order type: {order.order_type}")

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price += self.slippage
        else:
            fill_price -= self.slippage

        # Signed quantity: + for buy, − for sell
        signed_qty = order.quantity if order.side == OrderSide.BUY else -order.quantity

        commission = self._calc_commission(order.quantity, fill_price)

        fill = Fill(
            symbol=order.symbol,
            quantity=signed_qty,
            price=fill_price,
            commission=commission,
        )
        self._fills.append(fill)
        return fill

    def match_pending(self, bar: dict[str, Any]) -> list[Fill]:
        """Match all pending orders against *bar* and clear the queue.

        Returns the list of fills generated.
        """
        fills = []
        for order in self._pending_orders:
            fill = self.match_order(order, bar)
            if fill is not None:
                fills.append(fill)
        self._pending_orders.clear()
        return fills

    def match_pending_for_symbol(
        self, symbol: str, bar: dict[str, Any]
    ) -> list[Fill]:
        """Match pending orders for *symbol* only, removing them from the queue.

        Returns the list of fills for that symbol.
        """
        matched: list[Order] = []
        fills: list[Fill] = []

        for order in self._pending_orders:
            if order.symbol != symbol:
                continue
            fill = self.match_order(order, bar)
            if fill is not None:
                fills.append(fill)
                matched.append(order)

        # Remove matched orders
        for order in matched:
            self._pending_orders.remove(order)

        return fills

    # ------------------------------------------------------------------
    #  Commission
    # ------------------------------------------------------------------

    def _calc_commission(self, quantity: float, price: float) -> float:
        """Calculate commission for a trade.

        Formula: max(commission_rate × quantity × price, min_commission).
        """
        raw = self.commission_rate * quantity * price
        return max(raw, self.min_commission)

    def calculate_commission(self, quantity: float, price: float) -> float:
        """Public helper — same as internal calculation."""
        return self._calc_commission(quantity, price)

    # ------------------------------------------------------------------
    #  Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear pending orders and fill history."""
        self._pending_orders.clear()
        self._fills.clear()
