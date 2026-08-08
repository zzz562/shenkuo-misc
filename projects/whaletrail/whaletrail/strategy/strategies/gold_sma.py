"""Gold SMA crossover strategy.

A specialised variant of the dual-moving-average crossover tuned for gold
(XAU) daily bars.  It uses default SMA windows of 20 and 50 periods.

Rules
-----
- **Golden cross** (fast SMA crosses **above** slow SMA):
  ``order_target_percent(symbol, 0.8)`` — allocate 80 % of equity.
- **Death cross** (fast SMA crosses **below** slow SMA):
  ``order_target_percent(symbol, 0.0)`` — liquidate position.
"""

from __future__ import annotations

from typing import Optional

from whaletrail.strategy.base import Strategy


class GoldSMAStrategy(Strategy):
    """Gold SMA crossover strategy with default 20/50 periods."""

    FAST: int = 20
    SLOW: int = 50
    TARGET_PERCENT: float = 0.8

    def __init__(self, fast: int = FAST, slow: int = SLOW) -> None:
        super().__init__(name="gold_sma")
        self.fast = fast
        self.slow = slow

        # Per-symbol rolling windows of closes.
        self._windows: dict[str, list[float]] = {}

        # Track previous SMA values so we can detect crosses.
        self._prev_fast_sma: dict[str, Optional[float]] = {}
        self._prev_slow_sma: dict[str, Optional[float]] = {}

    # ------------------------------------------------------------------
    # Strategy logic
    # ------------------------------------------------------------------

    def on_bar(self, symbol: str, bar: dict) -> None:
        close = bar.get("close")
        if close is None:
            return

        # Update rolling window.
        window = self._windows.setdefault(symbol, [])
        window.append(float(close))
        # Keep only enough bars for the slowest SMA.
        if len(window) > self.slow:
            window.pop(0)

        # Not enough data yet.
        if len(window) < self.slow:
            return

        # Compute current SMAs.
        fast_sma = self._sma(window, self.fast)
        slow_sma = self._sma(window, self.slow)

        prev_fast = self._prev_fast_sma.get(symbol)
        prev_slow = self._prev_slow_sma.get(symbol)

        # Store for next bar.
        self._prev_fast_sma[symbol] = fast_sma
        self._prev_slow_sma[symbol] = slow_sma

        # Need at least one prior bar to detect a cross.
        if prev_fast is None or prev_slow is None:
            return

        # Golden cross: fast crosses above slow.
        if prev_fast <= prev_slow and fast_sma > slow_sma:
            self.order_target_percent(symbol, self.TARGET_PERCENT)

        # Death cross: fast crosses below slow.
        elif prev_fast >= prev_slow and fast_sma < slow_sma:
            self.order_target_percent(symbol, 0.0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _sma(window: list[float], period: int) -> float:
        """Simple moving average over the last *period* elements."""
        if len(window) < period:
            return sum(window) / len(window)
        return sum(window[-period:]) / period
