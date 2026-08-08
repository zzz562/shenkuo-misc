"""Performance metrics for a completed backtest run."""

from __future__ import annotations

import math
from typing import Any


def calculate_metrics(
    trades: list[dict[str, Any]],
    equity_curve: list[float],
    initial_cash: float,
) -> dict[str, Any]:
    """Compute a standard suite of performance metrics.

    Parameters
    ----------
    trades : list[dict]
        List of trade records.  Each dict must contain at least ``pnl``
        (realised profit/loss) and ``side`` (``"buy"`` or ``"sell"``).
    equity_curve : list[float]
        Daily or per-bar equity values in chronological order.  The first
        element should equal *initial_cash* before any trades.
    initial_cash : float
        Starting portfolio cash.

    Returns
    -------
    dict
        Keys:
        - ``total_return`` (float): percentage return (e.g. 12.5 for 12.5 %).
        - ``annual_return`` (float): annualised percentage return.
        - ``sharpe_ratio`` (float): annualised Sharpe ratio (risk-free = 2 %).
        - ``max_drawdown`` (float): maximum drawdown as a negative percentage.
        - ``win_rate`` (float): fraction of winning **closing** trades (0–1).
        - ``profit_factor`` (float): gross profit / gross loss.
        - ``total_trades`` (int): total number of executed trades.
        - ``total_return_abs`` (float): final equity minus initial cash.
        - ``volatility`` (float): annualised daily return volatility.
    """
    result: dict[str, Any] = {
        "total_return": 0.0,
        "annual_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "total_trades": len(trades),
        "total_return_abs": 0.0,
        "volatility": 0.0,
    }

    if not equity_curve or len(equity_curve) < 2:
        return result

    # ---- Total return ---------------------------------------------------
    final_equity = equity_curve[-1]
    total_return_abs = final_equity - initial_cash
    total_return_pct = (final_equity / initial_cash - 1.0) * 100.0

    result["total_return"] = round(total_return_pct, 4)
    result["total_return_abs"] = round(total_return_abs, 4)

    # ---- Annualised return ----------------------------------------------
    trading_days = len(equity_curve) - 1  # number of periods
    if trading_days > 0:
        annual_return_pct = (
            (final_equity / initial_cash) ** (252.0 / trading_days) - 1.0
        ) * 100.0
    else:
        annual_return_pct = 0.0

    result["annual_return"] = round(annual_return_pct, 4)

    # ---- Daily (period) returns -----------------------------------------
    daily_returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        if prev > 0:
            daily_returns.append(equity_curve[i] / prev - 1.0)
        else:
            daily_returns.append(0.0)

    # ---- Max drawdown ---------------------------------------------------
    peak = equity_curve[0]
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (val - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    result["max_drawdown"] = round(max_dd * 100.0, 4)

    # ---- Sharpe ratio ---------------------------------------------------
    # Assume 252 trading days, risk-free rate = 0.02.
    rf_daily = 0.02 / 252.0
    if len(daily_returns) > 1:
        mean_ret = sum(daily_returns) / len(daily_returns)
        excess = mean_ret - rf_daily
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (
            len(daily_returns) - 1
        )
        std_daily = math.sqrt(variance) if variance > 0 else 0.0
        result["volatility"] = round(std_daily * math.sqrt(252.0) * 100.0, 4)

        if std_daily > 0:
            sharpe = (excess / std_daily) * math.sqrt(252.0)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    result["sharpe_ratio"] = round(sharpe, 4)

    # ---- Win rate & profit factor ---------------------------------------
    # Consider *sell* trades (closing trades) for realised P&L.
    closing_trades = [t for t in trades if t.get("side") == "sell"]
    if closing_trades:
        wins = [t for t in closing_trades if (t.get("pnl") or 0.0) > 0]
        losses = [t for t in closing_trades if (t.get("pnl") or 0.0) < 0]
        win_rate = len(wins) / len(closing_trades)
        gross_profit = sum(t.get("pnl", 0.0) for t in wins)
        gross_loss = abs(sum(t.get("pnl", 0.0) for t in losses))

        result["win_rate"] = round(win_rate, 4)
        result["profit_factor"] = (
            round(gross_profit / gross_loss, 4) if gross_loss > 0 else float("inf")
        )
    else:
        result["win_rate"] = 0.0
        result["profit_factor"] = 0.0

    return result
