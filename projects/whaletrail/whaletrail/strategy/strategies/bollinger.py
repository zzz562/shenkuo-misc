from __future__ import annotations

from typing import Optional
"""Bollinger Bands breakout strategy."""
from whaletrail.strategy.base import Strategy


class BollingerStrategy(Strategy):
    """Buy when price breaks above upper band, sell when below lower band.

    Uses 20-period SMA with 2 standard deviation bands.
    """

    def __init__(self, period=20, std_dev=2.0, target_percent=0.8):
        super().__init__(name=f"bollinger_{period}_{std_dev}")
        self.period = period
        self.std_dev = std_dev
        self.target_percent = target_percent
        self._windows: dict[str, list[float]] = {}

    def on_bar(self, symbol, bar):
        close = bar["close"]
        w = self._windows.setdefault(symbol, [])
        w.append(close)
        if len(w) > self.period:
            w.pop(0)
        if len(w) < self.period:
            return

        sma = sum(w) / self.period
        variance = sum((x - sma) ** 2 for x in w) / self.period
        std = variance ** 0.5
        upper = sma + self.std_dev * std
        lower = sma - self.std_dev * std

        pos = self.account.positions.get(symbol)
        holding = pos is not None and pos.quantity > 0

        if close > upper and not holding:
            self.order_target_percent(symbol, self.target_percent)
        elif close < lower and holding:
            self.order_target_percent(symbol, 0.0)


def get_live_signal(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    state: dict,
    symbol: str,
) -> Optional[str]:
    """Paper-live signal: Bollinger Bands breakout."""
    period, k = 20, 2.0
    if len(closes) < period + 1:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    std = var ** 0.5
    upper, lower = mean + k * std, mean - k * std
    c, prev = closes[-1], closes[-2]
    from whaletrail.strategy.base import position_key
    pos = state.get("positions", {}).get(position_key(symbol, "bollinger"))
    holding = pos is not None
    if prev <= upper and c > upper and not holding:
        return "BUY"
    if prev >= lower and c < lower and holding:
        return "SELL"
    if holding and prev >= mean and c < mean:
        return "SELL"
    return None
