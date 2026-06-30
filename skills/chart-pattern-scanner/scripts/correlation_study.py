"""Cross-sectional / time-series correlation study for DFM (non-candlestick).

Studies the structure of a multi-symbol daily series:
- **Lag-1 autocorrelation** of returns (per stock + pooled): negative => mean
  reversion, positive => momentum. Quantifies the mean-reversion seen via candles.
- **Pairwise return correlation**: most-correlated pairs (pair-trade candidates)
  and the average co-movement of the market.
- **Beta to the market factor** (equal-weight cross-sectional mean return).
- **Lead-lag**: corr(market return[t-1], stock return[t]) — does the market lead?

Pure functions (pct_returns, pearson, lag1_autocorr, lead_lag, top_pairs,
market_factor) are unit-tested offline.
"""

from __future__ import annotations

import argparse
import json
import sys


def pct_returns(closes: list) -> list:
    """Daily simple returns; length len(closes)-1."""
    out = []
    for i in range(1, len(closes)):
        p = closes[i - 1]
        out.append((closes[i] - p) / p if p else 0.0)
    return out


def pearson(xs: list, ys: list) -> float | None:
    """Pearson correlation; None if <3 points or zero variance."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / (sxx**0.5 * syy**0.5)


def lag1_autocorr(returns: list) -> float | None:
    """corr(r[t], r[t-1]). Negative => mean reversion."""
    if len(returns) < 4:
        return None
    return pearson(returns[1:], returns[:-1])


def lead_lag(driver: list, target: list, lag: int = 1) -> float | None:
    """corr(driver[t-lag], target[t]) over aligned, equal-length series."""
    if lag <= 0 or len(driver) != len(target) or len(driver) <= lag + 2:
        return None
    return pearson(driver[:-lag], target[lag:])


def returns_by_date(bars: list) -> dict:
    """{date: simple return} computed over consecutive stored bars."""
    out = {}
    for i in range(1, len(bars)):
        p = bars[i - 1]["close"]
        if p:
            out[bars[i]["date"]] = (bars[i]["close"] - p) / p
    return out


def market_factor(ret_maps: dict) -> dict:
    """Equal-weight cross-sectional mean return per date across all symbols."""
    bucket: dict = {}
    for rmap in ret_maps.values():
        for d, r in rmap.items():
            bucket.setdefault(d, []).append(r)
    return {d: sum(v) / len(v) for d, v in bucket.items()}


def _aligned(a: dict, b: dict) -> tuple:
    dates = sorted(set(a) & set(b))
    return [a[d] for d in dates], [b[d] for d in dates]


def top_pairs(ret_maps: dict, min_overlap: int = 120, top: int = 12) -> list:
    """Most-correlated symbol pairs by return correlation (overlap >= min_overlap)."""
    syms = list(ret_maps)
    pairs = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            xs, ys = _aligned(ret_maps[syms[i]], ret_maps[syms[j]])
            if len(xs) >= min_overlap:
                r = pearson(xs, ys)
                if r is not None:
                    pairs.append((round(r, 3), syms[i], syms[j], len(xs)))
    pairs.sort(reverse=True)
    return pairs[:top]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="DFM correlation / structure study.")
    p.add_argument("--series-json", default="reports/dfm_history/_all_series.json")
    p.add_argument("--min-bars", type=int, default=120)
    p.add_argument("--top", type=int, default=12)
    args = p.parse_args(argv)

    try:
        raw = json.load(open(args.series_json, encoding="utf-8"))
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    ret_maps = {s: returns_by_date(b) for s, b in raw.items() if len(b) >= args.min_bars}
    ret_maps = {s: m for s, m in ret_maps.items() if len(m) >= args.min_bars}
    mkt = market_factor(ret_maps)
    mkt_dates = sorted(mkt)
    mkt_series = [mkt[d] for d in mkt_dates]

    # per-stock autocorr + beta to market
    autos, betas = [], []
    for s, m in ret_maps.items():
        a = lag1_autocorr([m[d] for d in sorted(m)])
        if a is not None:
            autos.append(a)
        xs, ys = _aligned(mkt, m)
        b = pearson(xs, ys)
        if b is not None:
            betas.append((round(b, 3), s))

    pooled_auto = sum(autos) / len(autos) if autos else None
    mkt_auto = lag1_autocorr(mkt_series)
    # market lead-lag: market[t-1] -> market[t] already in mkt_auto; market -> avg stock next day
    ll = []
    for s, m in ret_maps.items():
        xs, ys = _aligned(mkt, m)
        v = lead_lag(xs, ys, 1)
        if v is not None:
            ll.append(v)
    pooled_leadlag = sum(ll) / len(ll) if ll else None

    tp = top_pairs(ret_maps, min_overlap=args.min_bars, top=args.top)

    print(f"=== DFM correlation study: {len(ret_maps)} symbols ===")
    print(f"Avg lag-1 autocorrelation (per stock):  {pooled_auto:+.3f}   (<0 = mean-reverting)")
    print(f"Market-factor lag-1 autocorrelation:     {mkt_auto:+.3f}")
    print(f"Market->stock next-day lead-lag (avg):   {pooled_leadlag:+.3f}")
    print("\nMost / least market-correlated stocks (beta-corr):")
    betas.sort(reverse=True)
    for b, s in betas[:5]:
        print(f"   high  {s:13s} {b:+.2f}")
    for b, s in betas[-5:]:
        print(f"   low   {s:13s} {b:+.2f}")
    print(f"\nTop {args.top} correlated pairs (pair-trade candidates):")
    for r, a, b, n in tp:
        print(f"   {a:13s} ~ {b:13s} r={r:+.2f} (n={n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
