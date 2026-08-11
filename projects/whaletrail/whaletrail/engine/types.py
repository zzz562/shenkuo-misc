"""Shared types used by engine and strategy — no circular imports."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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
        quantity: Signed quantity (+ for buy, - for sell).
        price: Execution price per share.
        commission: Commission charged for this fill.
    """

    symbol: str
    quantity: float
    price: float
    commission: float = 0.0
