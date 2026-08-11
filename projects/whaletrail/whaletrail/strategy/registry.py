"""Unified strategy registry — single source of truth for all entry points.

Usage::

    from whaletrail.strategy.registry import get_strategy_class, list_strategies,
        STRATEGY_SIGNAL_FNS

    cls = get_strategy_class("gold_sma")
    strategy = cls()
"""

from __future__ import annotations

from typing import Callable, Optional, Type

from whaletrail.strategy.base import Strategy

# ---------------------------------------------------------------------------
# Strategy class registry (used by run-backtest.py, cli.py, paper-live.py)
# ---------------------------------------------------------------------------

from whaletrail.strategy.strategies.bollinger import BollingerStrategy
from whaletrail.strategy.strategies.gold_sma import GoldSMAStrategy
from whaletrail.strategy.strategies.gold_sma_v2 import GoldSMAStrategyV2
from whaletrail.strategy.strategies.ma_cross import MACrossStrategy
from whaletrail.strategy.strategies.momentum import MomentumStrategy
from whaletrail.strategy.strategies.turtle import TurtleStrategy

STRATEGY_CLASSES: dict[str, Type[Strategy]] = {
    "gold_sma": GoldSMAStrategy,
    "gold_sma_v2": GoldSMAStrategyV2,
    "ma_cross": MACrossStrategy,
    "bollinger": BollingerStrategy,
    "momentum": MomentumStrategy,
    "turtle": TurtleStrategy,
}


def get_strategy_class(name: str) -> Type[Strategy]:
    """Return the Strategy *class* for the given name."""
    cls = STRATEGY_CLASSES.get(name)
    if cls is None:
        available = ", ".join(sorted(STRATEGY_CLASSES))
        raise KeyError(f"Unknown strategy '{name}'. Available: {available}")
    return cls


def list_strategies() -> list[str]:
    """Return sorted list of registered strategy names."""
    return sorted(STRATEGY_CLASSES)


# ---------------------------------------------------------------------------
# Signal function registry (used by paper-live.py for live scanning)
# ---------------------------------------------------------------------------
# Each signal function receives (closes, highs, lows, state, symbol) and returns
# an Optional[str]: "BUY", "SELL", or None (no signal).

SignalFn = Callable[
    [list[float], list[float], list[float], dict, str], Optional[str]
]

STRATEGY_SIGNAL_FNS: dict[str, SignalFn] = {}
