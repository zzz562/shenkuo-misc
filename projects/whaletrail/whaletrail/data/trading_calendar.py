"""A-share trading calendar from the official SZSE API, cached locally.

SSE and SZSE share one official holiday schedule, including make-up trading
days on shifted weekends (调休). The Shenzhen exchange publishes it per
calendar month at
``https://www.szse.cn/api/report/exchange/onepersistenthour/monthList``
with rows ``{jyrq: YYYY-MM-DD, jybz: 0|1}`` (``jybz == "1"`` = trading day).

The calendar is cached in ``data_cache/trading_calendar_cn.txt`` (git-ignored)
so the daily cron works offline; only missing months are fetched. Months the
exchange has not yet announced (e.g. January before the next year's schedule
is published) fall back to a weekday heuristic.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

SZSE_URL = "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList"
CACHE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data_cache"
    / "trading_calendar_cn.txt"
)
_CN_TZ = ZoneInfo("Asia/Shanghai")
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today() -> date:
    return datetime.now(_CN_TZ).date()


def _month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _next_month(ym: str) -> str:
    year, month = int(ym[:4]), int(ym[5:7])
    month += 1
    if month > 12:
        year, month = year + 1, 1
    return f"{year:04d}-{month:02d}"


class TradingCalendar:
    """A-share trading-day calendar backed by the SZSE API + local cache."""

    def __init__(self, cache_path: Path | None = None, timeout: int = 15) -> None:
        self.cache_path = cache_path or CACHE_PATH
        self.timeout = timeout
        self._trading: set[date] = set()
        self._months: set[str] = set()  # months authoritatively covered
        self._load_cache()

    # ── public ────────────────────────────────────────────────────
    def is_trading_day(self, d: date | None = None) -> bool:
        """True if *d* (default: today in China time) is an A-share trading day.

        Falls back to a weekday heuristic when the month is not covered (no
        cache, fetch failed, or the exchange has not announced it yet).
        """
        d = d or _today()
        if self._ensure_covered(_month_of(d)):
            return d in self._trading
        return d.weekday() < 5

    # ── coverage / fetch ──────────────────────────────────────────
    def _ensure_covered(self, ym: str) -> bool:
        """Make sure month *ym* is in the cache, fetching it if needed.

        Returns True when the month is authoritatively covered.
        """
        if ym in self._months:
            return True
        try:
            for m in (ym, _next_month(ym)):  # holidays can span a boundary
                trading = self._fetch_month(m)
                if not trading:
                    continue  # month not announced yet; leave uncovered
                self._trading |= trading
                self._months.add(m)
            if self._months:
                self._write_cache()
        except Exception as exc:
            print(f"  ⚠️ A 股交易日历获取失败: {exc}")
        return ym in self._months

    def _fetch_month(self, ym: str) -> set[date]:
        resp = requests.get(
            SZSE_URL,
            params={"month": ym},
            headers={"User-Agent": _UA},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        rows = resp.json().get("data") or []
        return {
            date.fromisoformat(row["jyrq"])
            for row in rows
            if str(row.get("jybz")) == "1"
        }

    # ── cache ─────────────────────────────────────────────────────
    def _load_cache(self) -> None:
        if not self.cache_path.exists():
            return
        try:
            lines = self.cache_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            line = line.strip()
            if line.startswith("# months"):
                self._months.update(m for m in line.split(None, 2)[2].split(",") if m)
                continue
            if _DATE_RE.match(line):
                self._trading.add(date.fromisoformat(line))

    def _write_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            f"# szse trading calendar; fetched {_today().isoformat()}",
            f"# months {','.join(sorted(self._months))}",
        ]
        lines = header + sorted(d.isoformat() for d in self._trading)
        self.cache_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
