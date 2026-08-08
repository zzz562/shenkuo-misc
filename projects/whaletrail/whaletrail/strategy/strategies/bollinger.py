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
