"""Dual moving-average crossover strategy.

A general-purpose strategy that trades any symbol based on a fast / slow
SMA crossover.  Configurable periods default to 20 / 50.

Rules
-----
- **Golden cross** (fast SMA crosses **above** slow SMA):
  go long with 80 % of portfolio equity.
- **Death cross** (fast SMA crosses **below** slow SMA):
  liquidate position.
"""

from __future__ import annotations

from typing import Optional

from whaletrail.strategy.base import Strategy


class MACrossStrategy(Strategy):
    """Dual moving-average crossover for any symbol."""

    DEFAULT_FAST: int = 20
    DEFAULT_SLOW: int = 50
    TARGET_PERCENT: float = 0.8

    def __init__(
        self,
        fast: int = DEFAULT_FAST,
        slow: int = DEFAULT_SLOW,
        target_percent: float = TARGET_PERCENT,
    ) -> None:
        super().__init__(name="ma_cross")
        self.fast = fast
        self.slow = slow
        self.target_percent = target_percent

        self._windows: dict[str, list[float]] = {}
        self._prev_fast_sma: dict[str, Optional[float]] = {}
        self._prev_slow_sma: dict[str, Optional[float]] = {}

    # ------------------------------------------------------------------
    # Strategy logic
    # ------------------------------------------------------------------

    def on_bar(self, symbol: str, bar: dict) -> None:
        close = bar.get("close")
        if close is None:
            return

        # Accumulate rolling close history.
        window = self._windows.setdefault(symbol, [])
        window.append(float(close))
        if len(window) > self.slow:
            window.pop(0)

        if len(window) < self.slow:
            return  # not enough data

        fast_sma = self._sma(window, self.fast)
        slow_sma = self._sma(window, self.slow)

        prev_fast = self._prev_fast_sma.get(symbol)
        prev_slow = self._prev_slow_sma.get(symbol)

        self._prev_fast_sma[symbol] = fast_sma
        self._prev_slow_sma[symbol] = slow_sma

        if prev_fast is None or prev_slow is None:
            return

        # Golden cross
        if prev_fast <= prev_slow and fast_sma > slow_sma:
            self.order_target_percent(symbol, self.target_percent)

        # Death cross
        elif prev_fast >= prev_slow and fast_sma < slow_sma:
            self.order_target_percent(symbol, 0.0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _sma(window: list[float], period: int) -> float:
        if len(window) < period:
            return sum(window) / len(window)
        return sum(window[-period:]) / period

    def __repr__(self) -> str:
        return (
            f"MACrossStrategy(fast={self.fast}, slow={self.slow}, "
            f"target={self.target_percent:.0%})"
        )
