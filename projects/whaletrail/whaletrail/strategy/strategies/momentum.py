from __future__ import annotations

from typing import Optional
"""Momentum rotation strategy — go long when momentum is positive."""
from whaletrail.strategy.base import Strategy


class MomentumStrategy(Strategy):
    """Buy when N-period return is positive, sell when it turns negative.

    Simple trend-following: hold when momentum > 0, exit when < 0.
    """

    def __init__(self, period=20, threshold=0.0, target_percent=0.8):
        super().__init__(name=f"momentum_{period}")
        self.period = period
        self.threshold = threshold
        self.target_percent = target_percent
        self._closes: dict[str, list[float]] = {}

    def on_bar(self, symbol, bar):
        c = bar["close"]
        closes = self._closes.setdefault(symbol, [])
        closes.append(c)
        if len(closes) > self.period:
            closes.pop(0)
        if len(closes) < self.period:
            return

        momentum = (c - closes[0]) / closes[0]
        pos = self.account.positions.get(symbol)
        holding = pos is not None and pos.quantity > 0

        if momentum > self.threshold and not holding:
            self.order_target_percent(symbol, self.target_percent)
        elif momentum <= self.threshold and holding:
            self.order_target_percent(symbol, 0.0)


def get_live_signal(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    state: dict,
    symbol: str,
) -> Optional[str]:
    """Paper-live signal: momentum crossover."""
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
