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


def volume_zscore(volumes: list[float], period: int = 20) -> Optional[float]:
    """Z-score of the latest volume against the trailing *period* sessions.

    The lookback excludes the latest value itself (population std).
    Returns None when data is insufficient or the std is zero.
    """
    if len(volumes) < period + 1:
        return None
    window = [float(v) for v in volumes[-period - 1 : -1]]
    mean = sum(window) / period
    var = sum((v - mean) ** 2 for v in window) / period
    std = var ** 0.5
    if std <= 0:
        return None
    return (float(volumes[-1]) - mean) / std


def is_breakout(closes: list[float], period: int = 20) -> bool:
    """True when the latest close exceeds the highest close of the prior
    *period* sessions (prior window excludes the latest close)."""
    if len(closes) < period + 1:
        return False
    return closes[-1] > max(closes[-period - 1 : -1])


def whale_flag(
    closes: list[float],
    volumes: list[float],
    period: int = 20,
    z_threshold: float = 2.0,
) -> bool:
    """Cheap volume–price anomaly proxy for whale/跟庄 watching.

    Flags a volume surge (z ≥ *z_threshold*) coinciding with a *period*-day
    closing breakout.  This is a price/volume trend proxy, not actual
    order-flow (龙虎榜/大单) data.
    """
    z = volume_zscore(volumes, period)
    return z is not None and z >= z_threshold and is_breakout(closes, period)
