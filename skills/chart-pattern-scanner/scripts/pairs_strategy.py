"""Pairs / spread (relative-value) strategy for two co-moving DFM symbols.

Built for the strongest DFM pair found by the correlation study,
**EMAAR ~ EMAARDEV** (return correlation ≈ +0.67 on the bulletin), but works for
any two symbols in a series JSON.

Idea: two structurally linked names share a long-run price ratio. Trade the
*spread* (log price ratio), not the direction of the market:

- **Spread** = log(P_a / P_b); z-score it over a rolling `lookback` window.
- **Entry:** |z| >= `entry_z` — the ratio is stretched. z>0 (A rich vs B) =>
  SHORT_SPREAD (short A / long B); z<0 => LONG_SPREAD (long A / short B).
- **Exit:** |z| <= `exit_z` (reverted), or |z| >= `stop_z` (divergence stop).
- Market-neutral: P&L = leg-A return minus leg-B return in the trade's
  direction; the overall market drop/rise cancels out.

⚠️ **DFM short constraint:** retail shorting on DFM is limited, so the short leg
may not be executable for every account — treat the spread P&L as the
relative-value edge and, if you can only go long, hold the *cheaper* leg
(the one the signal would buy) and lighten the *richer* leg you already own.

Pure functions (log_ratio, rolling_z, align_closes, run_pairs_backtest,
current_pair_signal) are unit-tested offline.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from correlation_study import pct_returns, pearson  # noqa: E402


def log_ratio(a_closes: list, b_closes: list) -> list:
    """log(P_a / P_b) elementwise over equal-length aligned closes."""
    return [math.log(a / b) for a, b in zip(a_closes, b_closes)]


def rolling_z(series: list, lookback: int) -> list:
    """Rolling z-score aligned to series; None until warmed up or zero variance.

    z[i] = (series[i] - mean(window)) / std(window) over the trailing `lookback`
    points ending at i (population std).
    """
    out: list = [None] * len(series)
    if lookback < 2:
        return out
    for i in range(lookback - 1, len(series)):
        window = series[i - lookback + 1 : i + 1]
        mean = sum(window) / lookback
        var = sum((x - mean) ** 2 for x in window) / lookback
        if var <= 0:
            continue
        out[i] = (series[i] - mean) / math.sqrt(var)
    return out


def align_closes(bars_a: list, bars_b: list) -> tuple:
    """Align two bar lists on common dates -> (dates, a_closes, b_closes)."""
    bmap = {b["date"]: b["close"] for b in bars_b}
    dates, ac, bc = [], [], []
    for bar in bars_a:
        d = bar["date"]
        if d in bmap and bar["close"] > 0 and bmap[d] > 0:
            dates.append(d)
            ac.append(bar["close"])
            bc.append(bmap[d])
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    return [dates[i] for i in order], [ac[i] for i in order], [bc[i] for i in order]


def run_pairs_backtest(
    dates: list,
    a_closes: list,
    b_closes: list,
    lookback: int = 20,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    stop_z: float = 4.0,
) -> dict:
    """Backtest the z-score spread strategy. Market-neutral, additive P&L."""
    spread = log_ratio(a_closes, b_closes)
    z = rolling_z(spread, lookback)
    trades: list = []
    pos = None  # {"side", "i", "a", "b"}

    def close(i: int, reason: str) -> None:
        nonlocal pos
        r_a = a_closes[i] / pos["a"] - 1
        r_b = b_closes[i] / pos["b"] - 1
        pnl = (r_a - r_b) if pos["side"] == "long_spread" else (r_b - r_a)
        trades.append(
            {
                "side": pos["side"],
                "entry_date": dates[pos["i"]],
                "exit_date": dates[i],
                "entry_z": round(pos["z"], 3),
                "exit_z": round(z[i], 3) if z[i] is not None else None,
                "pnl": round(pnl, 4),
                "held": i - pos["i"],
                "reason": reason,
            }
        )
        pos = None

    for i in range(len(spread)):
        if z[i] is None:
            continue
        if pos is None:
            if z[i] >= entry_z:
                pos = {"side": "short_spread", "i": i, "a": a_closes[i], "b": b_closes[i], "z": z[i]}
            elif z[i] <= -entry_z:
                pos = {"side": "long_spread", "i": i, "a": a_closes[i], "b": b_closes[i], "z": z[i]}
        else:
            if abs(z[i]) >= stop_z:
                close(i, "stop")
            elif abs(z[i]) <= exit_z:
                close(i, "converged")
    if pos is not None:
        close(len(spread) - 1, "open")

    n = len(trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    total = sum(t["pnl"] for t in trades)
    return {
        "n_trades": n,
        "win_rate": round(wins / n, 3) if n else None,
        "avg_pnl": round(total / n, 4) if n else None,
        "total_pnl": round(total, 4) if n else 0.0,
        "avg_hold_days": round(sum(t["held"] for t in trades) / n, 1) if n else 0.0,
        "trades": trades,
        "open_position": pos is not None,
    }


def scan_pairs(
    series: dict,
    min_corr: float = 0.5,
    min_overlap: int = 120,
    lookback: int = 20,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    stop_z: float = 4.0,
    top: int = 20,
    min_trades: int = 5,
) -> list:
    """Backtest the spread strategy on every sufficiently-correlated pair.

    Pre-filters candidate pairs by return correlation (>= min_corr, a structural
    sanity check) and overlap, backtests each, and returns the strongest by
    total market-neutral P&L.

    ⚠️ This scans many pairs, so the top of the list is subject to multiple-
    comparison bias — treat results as *candidates to investigate*, not proven
    edges. A pair is only credible if it also has a real economic link
    (same group, sector, or share class) and survives out-of-sample.
    """
    syms = [s for s, b in series.items() if len(b) >= min_overlap]
    # Precompute each symbol's {date: close} ONCE (positive closes only) instead
    # of rebuilding both maps inside align_closes for every one of the O(n^2)
    # pairs — the per-pair work becomes a set-intersection over hashed keys.
    cmaps = {s: {b["date"]: b["close"] for b in series[s] if b["close"] > 0} for s in syms}
    min_bars = max(min_overlap, lookback + 5)
    results = []
    for i in range(len(syms)):
        amap = cmaps[syms[i]]
        for j in range(i + 1, len(syms)):
            bmap = cmaps[syms[j]]
            dates = sorted(set(amap) & set(bmap))
            if len(dates) < min_bars:
                continue
            ac = [amap[d] for d in dates]
            bc = [bmap[d] for d in dates]
            corr = pearson(pct_returns(ac), pct_returns(bc))
            if corr is None or corr < min_corr:
                continue
            bt = run_pairs_backtest(dates, ac, bc, lookback, entry_z, exit_z, stop_z)
            if bt["n_trades"] < min_trades:
                continue
            results.append(
                {
                    "a": syms[i],
                    "b": syms[j],
                    "corr": round(corr, 3),
                    "n_trades": bt["n_trades"],
                    "win_rate": bt["win_rate"],
                    "avg_pnl": bt["avg_pnl"],
                    "total_pnl": bt["total_pnl"],
                    "n_bars": len(dates),
                }
            )
    results.sort(key=lambda r: (r["total_pnl"] or 0), reverse=True)
    return results[:top]


def current_pair_signal(
    a_closes: list, b_closes: list, lookback: int = 20, entry_z: float = 2.0
) -> dict:
    """Current spread state on the latest aligned bar."""
    spread = log_ratio(a_closes, b_closes)
    z = rolling_z(spread, lookback)
    last = z[-1] if z else None
    if last is None:
        return {"signal": "NONE", "z": None, "note": "insufficient data"}
    if last >= entry_z:
        sig = "SHORT_SPREAD (A rich vs B: short/lighten A, long/hold B)"
    elif last <= -entry_z:
        sig = "LONG_SPREAD (A cheap vs B: long/hold A, short/lighten B)"
    else:
        sig = "NEUTRAL (ratio in normal range)"
    return {"signal": sig, "z": round(last, 2), "ratio": round(a_closes[-1] / b_closes[-1], 4)}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Pairs / spread z-score strategy + backtest.")
    p.add_argument("--series-json", default="reports/dfm_bulletin/_all_series.json")
    p.add_argument("--a", default="EMAAR", help="First symbol (the 'A' leg)")
    p.add_argument("--b", default="EMAARDEV", help="Second symbol (the 'B' leg)")
    p.add_argument("--lookback", type=int, default=20)
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument("--exit-z", type=float, default=0.5)
    p.add_argument("--stop-z", type=float, default=4.0)
    p.add_argument(
        "--scan",
        action="store_true",
        help="Scan every correlated pair in the series for tradable spreads (ranked)",
    )
    p.add_argument("--min-corr", type=float, default=0.5, help="--scan: min return correlation")
    p.add_argument("--min-overlap", type=int, default=120, help="--scan: min overlapping bars")
    p.add_argument("--top", type=int, default=20, help="--scan: how many pairs to show")
    args = p.parse_args(argv)

    try:
        with open(args.series_json, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:  # ValueError covers malformed/truncated JSON
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.scan:
        ranked = scan_pairs(
            raw, args.min_corr, args.min_overlap, args.lookback,
            args.entry_z, args.exit_z, args.stop_z, args.top,
        )
        print(f"=== Pair scan: {len(raw)} symbols, corr>={args.min_corr}, top {args.top} ===")
        print("⚠️ Multiple-comparison bias — these are candidates to investigate, not proven edges.")
        print(f"{'pair':30s} {'corr':>6s} {'trades':>7s} {'win':>6s} {'totP&L':>8s}")
        for r in ranked:
            wr = f"{r['win_rate'] * 100:.0f}%" if r["win_rate"] is not None else "—"
            print(
                f"{r['a'] + '~' + r['b']:30s} {r['corr']:>6.2f} {r['n_trades']:>7d} "
                f"{wr:>6s} {r['total_pnl'] * 100:>7.0f}%"
            )
        return 0

    for sym in (args.a, args.b):
        if sym not in raw:
            print(f"Error: {sym} not in {args.series_json}", file=sys.stderr)
            return 1

    dates, ac, bc = align_closes(raw[args.a], raw[args.b])
    if len(dates) < args.lookback + 5:
        print(f"Error: only {len(dates)} common bars for {args.a}/{args.b}", file=sys.stderr)
        return 1

    bt = run_pairs_backtest(
        dates, ac, bc, args.lookback, args.entry_z, args.exit_z, args.stop_z
    )
    sig = current_pair_signal(ac, bc, args.lookback, args.entry_z)
    print(f"=== Pairs: {args.a} ~ {args.b} ({len(dates)} common bars) ===")
    print(
        f"Entry |z|>={args.entry_z} · exit |z|<={args.exit_z} · stop |z|>={args.stop_z} "
        f"· lookback {args.lookback}"
    )
    print(
        f"Trades: {bt['n_trades']} | win-rate: {bt['win_rate']} | "
        f"avg P&L/trade: {(bt['avg_pnl'] or 0) * 100:+.2f}% | avg hold: {bt['avg_hold_days']}d"
    )
    print(f"Total market-neutral P&L (additive): {bt['total_pnl'] * 100:+.1f}%")
    print(f"Current: {sig['signal']} (z={sig['z']}, ratio={sig.get('ratio')})")
    print("\n⚠️ Short leg may not be executable on DFM retail — see module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
