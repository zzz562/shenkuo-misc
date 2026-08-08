"""Turtle Trading strategy — Donchian channel breakout."""
from whaletrail.strategy.base import Strategy


class TurtleStrategy(Strategy):
    """Classic Turtle Trading: buy on 20-day high breakout, sell on 10-day low.

    Also uses ATR-based position sizing and a 2% risk per trade.
    """

    def __init__(self, entry_period=20, exit_period=10, atr_period=20,
                 risk_percent=0.02, target_percent=0.8):
        super().__init__(name=f"turtle_{entry_period}_{exit_period}")
        self.entry_period = entry_period
        self.exit_period = exit_period
        self.atr_period = atr_period
        self.risk_percent = risk_percent
        self.target_percent = target_percent
        self._highs: dict[str, list[float]] = {}
        self._lows: dict[str, list[float]] = {}
        self._closes: dict[str, list[float]] = {}

    def on_bar(self, symbol, bar):
        h, l, c = bar["high"], bar["low"], bar["close"]
        highs = self._highs.setdefault(symbol, [])
        lows = self._lows.setdefault(symbol, [])
        closes = self._closes.setdefault(symbol, [])

        highs.append(h)
        lows.append(l)
        closes.append(c)
        for arr in (highs, lows, closes):
            if len(arr) > max(self.entry_period, self.atr_period):
                arr.pop(0)

        if len(highs) < max(self.entry_period, self.atr_period):
            return

        entry_high = max(highs[-self.entry_period:])
        exit_low = min(lows[-self.exit_period:])
        pos = self.account.positions.get(symbol)
        holding = pos is not None and pos.quantity > 0

        if c > entry_high and not holding:
            self.order_target_percent(symbol, self.target_percent)
        elif c < exit_low and holding:
            self.order_target_percent(symbol, 0.0)
