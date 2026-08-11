"""Enhanced Gold SMA strategy — ATR stop-loss + risk-managed position sizing."""
from __future__ import annotations
from typing import Optional

from whaletrail.strategy.base import Strategy


class GoldSMAStrategyV2(Strategy):
    """Gold trend-following with ATR-based stop and dynamic sizing.

    Rules:
    - Entry: SMA(fast) crosses above SMA(slow) → long
    - Exit:  SMA(fast) crosses below SMA(slow) → close
           OR price drops below trailing ATR stop
    - Size: target_percent of portfolio, capped at risk_per_trade / ATR
    """

    def __init__(
        self,
        fast: int = 20,
        slow: int = 50,
        atr_period: int = 14,
        atr_stop_mult: float = 2.0,
        risk_per_trade: float = 0.02,  # 2% of equity per trade
        target_percent: float = 0.8,
        trend_filter: bool = True,  # require price > SMA(200) for longs
    ):
        super().__init__(name=f"gold_sma_v2_{fast}_{slow}")
        self.fast = fast
        self.slow = slow
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.risk_per_trade = risk_per_trade
        self.target_percent = target_percent
        self.trend_filter = trend_filter

        # Rolling windows
        self._closes: dict[str, list[float]] = {}
        self._highs: dict[str, list[float]] = {}
        self._lows: dict[str, list[float]] = {}
        # Trailing stop level per symbol
        self._stop_level: dict[str, float] = {}

    def _sma(self, values: list[float], period: int) -> float | None:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    def _atr(self, highs: list[float], lows: list[float], closes: list[float]) -> float | None:
        n = self.atr_period
        if len(highs) < n + 1 or len(lows) < n + 1 or len(closes) < n + 1:
            return None
        trs = []
        for i in range(-n, 0):
            h, l, pc = highs[i], lows[i], closes[i - 1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        return sum(trs) / n

    def on_bar(self, symbol: str, bar: dict) -> None:
        c, h, l = bar["close"], bar["high"], bar["low"]

        closes = self._closes.setdefault(symbol, [])
        highs = self._highs.setdefault(symbol, [])
        lows = self._lows.setdefault(symbol, [])
        closes.append(c)
        highs.append(h)
        lows.append(l)
        for arr in (closes, highs, lows):
            max_period = max(self.fast, self.slow, self.atr_period, 200)
            if len(arr) > max_period + 1:
                arr.pop(0)

        if len(closes) < self.slow + 1:
            return

        fast_curr = self._sma(closes, self.fast)
        slow_curr = self._sma(closes, self.slow)
        fast_prev = self._sma(closes[:-1], self.fast)
        slow_prev = self._sma(closes[:-1], self.slow)
        if None in (fast_curr, slow_curr, fast_prev, slow_prev):
            return

        atr = self._atr(highs, lows, closes) or 0
        pos = self.account.positions.get(symbol)
        holding = pos is not None and pos.quantity > 0
        equity = self.account.total_equity(self.current_prices)

        # ── Trend filter ─────────────────────────────────────
        trend_ok = True
        if self.trend_filter:
            sma200 = self._sma(closes, 200)
            if sma200 is not None:
                trend_ok = c > sma200

        # ── Entry ────────────────────────────────────────────
        bull_cross = fast_prev <= slow_prev and fast_curr > slow_curr
        if bull_cross and not holding and trend_ok:
            # Position sizing: risk_per_trade / ATR stops
            if atr > 0:
                risk_amount = equity * self.risk_per_trade
                stop_distance = self.atr_stop_mult * atr
                qty_risk = risk_amount / stop_distance if stop_distance > 0 else 0
                qty_pct = (equity * self.target_percent) / c if c > 0 else 0
                qty = min(qty_risk, qty_pct)
            else:
                qty = (equity * self.target_percent) / c if c > 0 else 0
            if qty > 0:
                self.buy(symbol, quantity=int(qty))
                self._stop_level[symbol] = c - self.atr_stop_mult * atr

        # ── Exit ─────────────────────────────────────────────
        if holding:
            bear_cross = fast_prev >= slow_prev and fast_curr < slow_curr
            stop_hit = (
                symbol in self._stop_level
                and c < self._stop_level[symbol]
            )
            if bear_cross or stop_hit:
                self.order_target_percent(symbol, 0.0)
                self._stop_level.pop(symbol, None)
            elif symbol in self._stop_level:
                # Trailing stop: ratchet up
                new_stop = c - self.atr_stop_mult * atr
                if new_stop > self._stop_level[symbol]:
                    self._stop_level[symbol] = new_stop


def get_live_signal(
    closes: list[float],
    highs: list[float],
    lows: list[float],
    state: dict,
    symbol: str,
) -> Optional[str]:
    """Paper-live signal: SMA20/50 + SMA200 trend filter + ATR trailing stop."""
    from whaletrail.indicators import atr, cross_signal, sma
    if len(closes) < 51:
        return None
    c = closes[-1]
    a = atr(highs, lows, closes, 14) or 0
    stops = state.setdefault("atr_stops", {})
    pos = state.get("positions", {}).get(symbol)
    holding = pos is not None and pos.get("side") == "LONG"
    stop = stops.get(symbol)
    if holding and stop is not None and c < stop:
        stops.pop(symbol, None)
        return "SELL"
    base = cross_signal(closes, 20, 50)
    sma200 = sma(closes, min(200, len(closes))) if len(closes) >= 50 else None
    if base == "BUY":
        if sma200 is not None and c < sma200:
            return None
        if a > 0:
            stops[symbol] = c - 2.0 * a
        return "BUY"
    if base == "SELL":
        stops.pop(symbol, None)
        return "SELL"
    if holding and a > 0 and stop is not None:
        new_stop = c - 2.0 * a
        if new_stop > stop:
            stops[symbol] = new_stop
    return None
