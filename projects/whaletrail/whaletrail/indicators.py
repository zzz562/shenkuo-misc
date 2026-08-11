"""Shared technical indicators used by strategies and paper-live scanning."""
from __future__ import annotations

from typing import Optional


def sma(values: list[float], period: int) -> Optional[float]:
    """Simple moving average over the last *period* elements."""
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> Optional[float]:
    """Average True Range."""
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(-period, 0):
        h, l, pc = highs[i], lows[i], closes[i - 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / period


def cross_signal(
    closes: list[float], fast: int, slow: int
) -> Optional[str]:
    """Detect SMA crossover: returns BUY on golden cross, SELL on death cross."""
    if len(closes) < slow + 1:
        return None
    f0, s0 = sma(closes, fast), sma(closes, slow)
    f1, s1 = sma(closes[:-1], fast), sma(closes[:-1], slow)
    if None in (f0, s0, f1, s1):
        return None
    if f1 <= s1 and f0 > s0:
        return "BUY"
    if f1 >= s1 and f0 < s0:
        return "SELL"
    return None
