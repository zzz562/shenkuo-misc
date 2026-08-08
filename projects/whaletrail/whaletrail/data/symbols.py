"""Symbol helpers for multi-market instrument identification.

Markets
-------
- CN  : A-shares (Shanghai / Shenzhen), e.g. "600519.SH", "000858.SZ"
- HK  : Hong Kong stocks, e.g. "00700.HK"
- US  : US equities, e.g. "AAPL", "TSLA"
- XAU : Gold futures / spot, e.g. "GC=F"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Market(str, Enum):
    """Supported trading markets."""

    CN = "cn"    # A-shares (Shanghai / Shenzhen)
    HK = "hk"    # Hong Kong stocks
    US = "us"    # US equities
    XAU = "xau"  # Gold / precious metals


@dataclass(frozen=True)
class Symbol:
    """Normalised instrument identifier.

    Attributes
    ----------
    raw : str
        Original user-supplied string.
    market : Market
        Deduced trading market.
    ticker : str
        Clean ticker suitable for the data source (e.g. ``"600519"`` for CN,
        ``"AAPL"`` for US).
    """

    raw: str
    market: Market
    ticker: str

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"Symbol(raw={self.raw!r}, market={self.market.value!r}, ticker={self.ticker!r})"


# ---------------------------------------------------------------------------
#  Parsing rules
# ---------------------------------------------------------------------------

# A-shares: 6 digits + .SH or .SZ
_RE_CN = re.compile(r"^(\d{6})\.(SH|SZ)$", re.IGNORECASE)

# Hong Kong: 1-5 digits + .HK
_RE_HK = re.compile(r"^(\d{1,5})\.HK$", re.IGNORECASE)

# Gold futures: GC=F (and variants)
_GOLD_TICKERS = frozenset({"GC=F", "XAUUSD=X", "GLD"})


def parse_symbol(raw: str) -> Symbol:
    """Parse a raw symbol string into a normalised :class:`Symbol`.

    Parameters
    ----------
    raw : str
        Input string such as ``"600519.SH"``, ``"00700.HK"``, ``"AAPL"``,
        or ``"GC=F"``.

    Returns
    -------
    Symbol

    Raises
    ------
    ValueError
        If *raw* cannot be matched to any known market convention.
    """
    raw_stripped = raw.strip()

    # -- Gold ---------------------------------------------------------------
    if raw_stripped.upper() in _GOLD_TICKERS:
        return Symbol(raw=raw_stripped, market=Market.XAU, ticker="GC=F")

    # -- A-shares -----------------------------------------------------------
    m = _RE_CN.match(raw_stripped)
    if m:
        code = m.group(1)
        return Symbol(raw=raw_stripped, market=Market.CN, ticker=code)

    # -- Hong Kong ----------------------------------------------------------
    m = _RE_HK.match(raw_stripped)
    if m:
        code = m.group(1)
        # Normalise to 5-digit HK code
        ticker = code.zfill(5)
        return Symbol(raw=raw_stripped, market=Market.HK, ticker=ticker)

    # -- US equities --------------------------------------------------------
    #  Heuristic: 1-5 uppercase letters, no dots
    if re.fullmatch(r"[A-Z]{1,5}", raw_stripped.upper()):
        return Symbol(raw=raw_stripped, market=Market.US, ticker=raw_stripped.upper())

    raise ValueError(
        f"Cannot parse symbol {raw_stripped!r}. "
        f"Expected formats: A-shares '600519.SH', HK '00700.HK', "
        f"US 'AAPL', or gold 'GC=F'."
    )
