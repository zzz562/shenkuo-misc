#!/usr/bin/env python3
"""Audit the Parquet data cache for wrong-instrument / price-scale corruption.

Run on the machine that owns the cache (Mac mini):

  python scripts/verify-cache.py                # report only
  python scripts/verify-cache.py --drop-invalid # delete violating files

Checks per cached symbol:
  - median close inside whaletrail.data.cache.PRICE_BOUNDS (wrong-scale guard)
  - monotonic date index, non-positive closes
Cross-symbol check when both GLD and GC=F are cached:
  - GLD / GC=F ratio on overlapping dates stays in [0.07, 0.13]
    (GLD tracks ~0.093 oz of gold).

Exit code 1 when any check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from whaletrail.data.cache import PRICE_BOUNDS, price_scale_violation  # noqa: E402

RATIO_PAIR = ("GLD", "GC=F")
RATIO_BOUNDS = (0.07, 0.13)


def _load(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        print(f"  ❌ {path.name}: unreadable ({exc})")
        return None
    if df.empty or "close" not in df.columns:
        print(f"  ❌ {path.name}: empty or missing 'close'")
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df.sort_index()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop-invalid",
        action="store_true",
        help="delete cache files that fail validation (next run re-downloads)",
    )
    args = parser.parse_args()

    cache_dir = ROOT / "data_cache"
    files = sorted(cache_dir.glob("*.parquet"))
    if not files:
        print(f"no parquet files under {cache_dir}")
        return 0

    failures: list[str] = []
    frames: dict[str, pd.DataFrame] = {}

    print(f"auditing {len(files)} cache file(s) in {cache_dir}\n")
    for path in files:
        symbol = path.stem
        df = _load(path)
        if df is None:
            failures.append(symbol)
            if args.drop_invalid:
                path.unlink(missing_ok=True)
            continue

        closes = df["close"].dropna()
        problems = []
        if (closes <= 0).any():
            problems.append(f"{int((closes <= 0).sum())} non-positive close(s)")
        if not df.index.is_monotonic_increasing:
            problems.append("date index not monotonic")
        violation = price_scale_violation(symbol, df)
        if violation is not None:
            problems.append(violation)

        status = "❌" if problems else "✅"
        bounds = PRICE_BOUNDS.get(symbol)
        bound_txt = f"[{bounds[0]}, {bounds[1]}]" if bounds else "no guard"
        detail = f"\n      ↳ {'; '.join(problems)}" if problems else ""
        print(
            f"  {status} {symbol:<10} rows={len(df):<5} "
            f"{df.index[0].date()} → {df.index[-1].date()}  "
            f"close {closes.min():.2f}–{closes.max():.2f} "
            f"(median {closes.median():.2f}, bounds {bound_txt}){detail}"
        )
        if problems:
            failures.append(symbol)
            if args.drop_invalid:
                path.unlink()
                print(f"      dropped {path.name}")
        else:
            frames[symbol] = df

    # Cross-instrument ratio check: GLD must track ~1/10 of gold futures.
    a, b = RATIO_PAIR
    if a in frames and b in frames:
        joined = frames[a][["close"]].join(
            frames[b][["close"]], how="inner", lsuffix="_a", rsuffix="_b"
        )
        if not joined.empty:
            ratio = (joined["close_a"] / joined["close_b"]).median()
            lo, hi = RATIO_BOUNDS
            ok = lo <= ratio <= hi
            print(
                f"\n  {'✅' if ok else '❌'} {a}/{b} median ratio {ratio:.4f} "
                f"(expect {lo}–{hi}) over {len(joined)} overlapping sessions"
            )
            if not ok:
                failures.append(f"{a}/{b} ratio")

    summary = {"checked": len(files), "failures": failures}
    print("\n" + json.dumps(summary, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
