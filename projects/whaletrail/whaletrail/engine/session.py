"""Real-time market session checks for live paper trading.

The backtest engine is calendar-driven (``TradingClock``); the live scripts use
this module to gate scans and paper trades on actual market sessions:

- US (NYSE): Mon–Fri 09:30–16:00 Eastern Time — ``paper-live.py`` (GLD / SPY).
- A-share (SSE/SZSE): 09:30–16:00 China Standard Time window —
  ``ashare-paper.py``. Whether a calendar day is an actual trading day
  (weekends, holidays, and make-up days on shifted weekends) is decided by
  ``whaletrail.data.trading_calendar.TradingCalendar`` (SZSE official
  calendar), not by the weekday here.

Holiday handling: US holidays are covered by the bar-freshness guard in
``paper-live.py`` (a bar from today is required), so no static calendar is
maintained here.

All functions accept tz-aware datetimes; naive ones are assumed to be in the
market's own timezone.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

US_TZ = ZoneInfo("America/New_York")
CN_TZ = ZoneInfo("Asia/Shanghai")

_US_SESSION_START = time(9, 30)
_US_SESSION_END = time(16, 0)
_CN_SESSION_START = time(9, 30)
_CN_SESSION_END = time(16, 0)  # extends past 15:00 close for the 15:30 CST cron


def _to_market_tz(now: datetime | None, tz: ZoneInfo) -> datetime:
    dt = now or datetime.now(tz)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def us_session(now: datetime | None = None) -> bool:
    """True during NYSE regular hours: Mon–Fri 09:30–16:00 ET."""
    dt = _to_market_tz(now, US_TZ)
    return dt.weekday() < 5 and _US_SESSION_START <= dt.time() < _US_SESSION_END


def ashare_hours(now: datetime | None = None) -> bool:
    """True within the A-share snapshot window: 09:30–16:00 CST, any day.

    Deliberately ignores weekdays: make-up Saturdays/Sundays (调休) are real
    trading days, so the trading-day decision belongs to ``TradingCalendar``.
    The 11:30–13:00 lunch break is not excluded: a midday snapshot is still a
    valid accumulation row for ``build_daily_history``.
    """
    dt = _to_market_tz(now, CN_TZ)
    return _CN_SESSION_START <= dt.time() < _CN_SESSION_END
