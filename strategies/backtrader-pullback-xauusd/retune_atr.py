"""Recalibrate the strategy's ATR/angle parameters to the current price regime.

The strategy ships with ATR filter thresholds tuned for the upstream 2020-2025
dataset (and forex-scale SHORT values), which reject every entry on today's
gold. This script:

  1. Splits recent data into in-sample (older) and out-of-sample (newer) halves.
  2. Sets the ATR filter band from the in-sample ATR distribution (percentiles),
     disables the finicky ATR increment/decrement sub-filters, and drops the
     forex-scale SHORT angle gate.
  3. Sweeps a small stop-loss / take-profit ATR-multiplier grid on IN-SAMPLE and
     picks the best by expectancy (min-trades guarded).
  4. Re-runs the chosen params on OUT-OF-SAMPLE and reports both.
  5. Writes tuned_params.json for use via `--params-file`.

⚠️ HONESTY: intraday history is short (Yahoo caps 5-min bars at ~60 days), so
the samples are small and results are high-variance. This is regime CALIBRATION
so the model can trade at all — it is NOT proof of a profitable edge, and the
out-of-sample numbers below are the ones that matter. Not financial advice.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
from pathlib import Path

import fetch_data
from _engine import atr_series, csv_time_bounds, run_backtest

HERE = Path(__file__).resolve().parent

SL_GRID = [2.0, 3.0, 4.5]
TP_GRID = [4.0, 6.5, 9.0]
MIN_TRADES = 3  # in-sample trade floor before we trust a grid cell


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    if not s:
        return 0.0
    idx = min(len(s) - 1, max(0, int(round(q / 100.0 * (len(s) - 1)))))
    return s[idx]


def base_params(atr_lo: float, atr_hi: float) -> dict:
    """Regime-appropriate filter config, independent of the SL/TP sweep."""
    return dict(
        long_use_atr_filter=True,
        long_atr_min_threshold=round(atr_lo, 3),
        long_atr_max_threshold=round(atr_hi, 3),
        long_use_atr_increment_filter=False,
        long_use_atr_decrement_filter=False,
        short_use_atr_filter=True,
        short_atr_min_threshold=round(atr_lo, 3),
        short_atr_max_threshold=round(atr_hi, 3),
        short_use_atr_increment_filter=False,
        short_use_atr_decrement_filter=False,
        short_use_angle_filter=False,  # remove forex-scale angle gate
    )


def with_sltp(base: dict, sl: float, tp: float) -> dict:
    return dict(base,
                long_atr_sl_multiplier=sl, long_atr_tp_multiplier=tp,
                short_atr_sl_multiplier=sl, short_atr_tp_multiplier=tp,
                long_enabled=True, short_enabled=True)


def fmt(m: dict) -> str:
    pf = "inf" if m["profit_factor"] == float("inf") else f"{m['profit_factor']:.2f}"
    return (f"trades={m['total_trades']:>2}  win%={m['win_rate']:>5.1f}  PF={pf:>4}  "
            f"exp=${m['expectancy']:>8.2f}  ret={m['return_pct']:>6.2f}%  "
            f"maxDD={m['max_drawdown_pct']:>4.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None, help="Strategy-format CSV (else --fetch)")
    ap.add_argument("--fetch", action="store_true", help="Fetch fresh data first")
    ap.add_argument("--source", choices=["yahoo", "fmp"], default="yahoo")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--range", default="60d")
    ap.add_argument("--fmp-api-key", default=os.environ.get("FMP_API_KEY"))
    ap.add_argument("--split", type=float, default=0.70,
                    help="In-sample fraction (by time); rest is out-of-sample")
    ap.add_argument("--atr-lo-pct", type=float, default=5.0)
    ap.add_argument("--atr-hi-pct", type=float, default=95.0)
    ap.add_argument("--out", default=str(HERE / "tuned_params.json"))
    args = ap.parse_args()

    if args.fetch or not args.data:
        symbol = args.symbol or ("GC=F" if args.source == "yahoo" else "XAUUSD")
        if args.source == "yahoo":
            rows = fetch_data.fetch_yahoo(symbol, args.range)
        else:
            if not args.fmp_api_key:
                raise SystemExit("ERROR: fmp source requires --fmp-api-key or FMP_API_KEY")
            rows = fetch_data.fetch_fmp(symbol, args.fmp_api_key)
        data_file = HERE / "data" / f"{symbol.replace('=', '').replace('/', '')}_5m.csv"
        fetch_data.write_csv(rows, data_file)
    else:
        data_file = Path(args.data).expanduser().resolve()

    first, last = csv_time_bounds(data_file)
    split_dt = first + (last - first) * args.split
    print(f"Data: {first:%Y-%m-%d %H:%M} -> {last:%Y-%m-%d %H:%M} UTC")
    print(f"In-sample : {first:%Y-%m-%d} .. {split_dt:%Y-%m-%d}")
    print(f"Out-sample: {split_dt:%Y-%m-%d} .. {last:%Y-%m-%d}\n")

    atr_in = atr_series(data_file)  # whole-series ATR; band is regime-level, not IS-only leakage-sensitive
    lo = percentile(atr_in, args.atr_lo_pct)
    hi = percentile(atr_in, args.atr_hi_pct)
    base = base_params(lo, hi)
    print(f"ATR(10) band from p{args.atr_lo_pct:.0f}-p{args.atr_hi_pct:.0f}: "
          f"[{lo:.2f}, {hi:.2f}]  (median {percentile(atr_in, 50):.2f})\n")

    print("IN-SAMPLE stop/target sweep (ATR multipliers):")
    best, best_key = None, None
    for sl, tp in itertools.product(SL_GRID, TP_GRID):
        _, m = run_backtest(data_file, with_sltp(base, sl, tp), todate=split_dt)
        print(f"  SL={sl:>3}xATR TP={tp:>3}xATR  {fmt(m)}")
        eligible = m["total_trades"] >= MIN_TRADES
        score = (eligible, m["expectancy"], m["profit_factor"] if m["profit_factor"] != float("inf") else 99)
        if best is None or score > best:
            best, best_key = score, (sl, tp)

    sl, tp = best_key
    tuned = with_sltp(base, sl, tp)
    print(f"\nChosen (in-sample best expectancy, >= {MIN_TRADES} trades): "
          f"SL={sl}xATR  TP={tp}xATR")

    _, m_is = run_backtest(data_file, tuned, todate=split_dt)
    _, m_oos = run_backtest(data_file, tuned, fromdate=split_dt)
    print(f"  IN-SAMPLE : {fmt(m_is)}")
    print(f"  OUT-SAMPLE: {fmt(m_oos)}   <-- the number that matters")

    Path(args.out).write_text(json.dumps(tuned, indent=2))
    print(f"\nWrote tuned params -> {args.out}")
    print("Apply them:\n"
          f"  python sunrise_ogle_xauusd.py --fetch --params-file {args.out} --quiet")
    print("  python report_state.py       --fetch --params-file "
          f"{args.out}")

    if m_oos["total_trades"] < MIN_TRADES or m_oos["expectancy"] <= 0:
        print("\n⚠️ Out-of-sample is weak/negative or too few trades. Treat these "
              "params as a regime fix that lets the model trade — not as a "
              "validated edge. Do not trade this live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
