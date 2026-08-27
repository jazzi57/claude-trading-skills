"""Report the strategy's CURRENT state on the most recent bar.

Runs the pullback state machine over the latest data and, at the final bar,
reports whether it is SCANNING / ARMED / WINDOW_OPEN (or already in a position)
plus the concrete breakout, stop-loss and take-profit price levels it would use.

This is a decision-support readout of a mechanical model on recent data. It is
NOT financial advice and NOT a vetted live signal — see the README caveats.

Examples
--------
    python report_state.py --fetch                       # fresh GC=F via Yahoo
    python report_state.py --fetch --no-atr-filter       # ignore regime filters
    python report_state.py --data data/GCF_5m.csv --json
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import fetch_data
from _engine import run_backtest

HERE = Path(__file__).resolve().parent


def _resolve_data(args) -> Path:
    if args.fetch:
        symbol = args.symbol or ("GC=F" if args.source == "yahoo" else "XAUUSD")
        if args.source == "yahoo":
            rows = fetch_data.fetch_yahoo(symbol, args.range)
        else:
            if not args.fmp_api_key:
                raise SystemExit("ERROR: --fetch --source fmp requires --fmp-api-key or FMP_API_KEY")
            rows = fetch_data.fetch_fmp(symbol, args.fmp_api_key)
        out = HERE / "data" / f"{symbol.replace('=', '').replace('/', '')}_5m.csv"
        fetch_data.write_csv(rows, out)
        return out
    if args.data:
        return Path(args.data).expanduser().resolve()
    raise SystemExit("ERROR: provide --data PATH or --fetch")


def build_report(strat) -> dict:
    """Read FSM state + levels off the strategy instance at the final bar."""
    bar_dt = strat.data.datetime.datetime(0).replace(tzinfo=timezone.utc)
    close = strat.data.close[0]
    high = strat.data.high[0]
    low = strat.data.low[0]
    atr = float(strat.atr[0])
    p = strat.p

    rpt = dict(
        as_of_utc=bar_dt.strftime("%Y-%m-%d %H:%M"),
        last_close=round(close, 2),
        atr=round(atr, 3),
        ema_fast=round(float(strat.ema_fast[0]), 2),
        ema_slow=round(float(strat.ema_slow[0]), 2),
        ema_filter=round(float(strat.ema_filter_price[0]), 2),
    )

    if strat.position:
        size = strat.position.size
        rpt.update(
            state="IN_POSITION",
            direction="LONG" if size > 0 else "SHORT",
            action="Manage open position (bracket stop/target already working).",
            entry_price=round(strat.position.price, 2),
            stop_loss=round(strat.stop_level, 2) if strat.stop_level else None,
            take_profit=round(strat.take_level, 2) if strat.take_level else None,
        )
        return rpt

    state = getattr(strat, "entry_state", "SCANNING")
    armed = getattr(strat, "armed_direction", None)

    if state == "WINDOW_OPEN":
        direction = armed or "?"
        brk = getattr(strat, "window_breakout_level", None)
        # Prospective bracket if the breakout triggers on the current bar.
        if direction == "LONG":
            sl = low - atr * p.long_atr_sl_multiplier
            tp = high + atr * p.long_atr_tp_multiplier
        else:
            sl = high + atr * p.short_atr_sl_multiplier
            tp = low - atr * p.short_atr_tp_multiplier
        rpt.update(
            state="WINDOW_OPEN",
            direction=direction,
            action=(f"Breakout window OPEN. Enter {direction} only if price breaks "
                    f"the breakout level; else the window expires with no trade."),
            breakout_level=round(brk, 2) if brk else None,
            window_top=round(strat.window_top_limit, 2) if strat.window_top_limit else None,
            window_bottom=round(strat.window_bottom_limit, 2) if strat.window_bottom_limit else None,
            prospective_stop_loss=round(sl, 2),
            prospective_take_profit=round(tp, 2),
        )
    elif state in ("ARMED_LONG", "ARMED_SHORT"):
        direction = state.split("_")[1]
        rpt.update(
            state=state,
            direction=direction,
            action=(f"Signal fired ({direction}); waiting for the pullback "
                    f"({'red' if direction == 'LONG' else 'green'} candles) before a "
                    f"breakout window opens. No entry level yet."),
        )
    else:
        rpt.update(
            state="SCANNING",
            direction=None,
            action="No setup. Flat and scanning for the next EMA-crossover signal.",
        )
    return rpt


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None, help="Strategy-format CSV")
    ap.add_argument("--fetch", action="store_true", help="Fetch fresh data first")
    ap.add_argument("--source", choices=["yahoo", "fmp"], default="yahoo")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--range", default="60d")
    ap.add_argument("--fmp-api-key", default=os.environ.get("FMP_API_KEY"))
    ap.add_argument("--direction", choices=["long", "short", "both"], default="both")
    ap.add_argument("--no-atr-filter", action="store_true",
                    help="Ignore the regime-specific ATR filters when evaluating state")
    ap.add_argument("--params-file", default=None,
                    help="JSON of strategy params to apply (e.g. from retune_atr.py)")
    ap.add_argument("--json", action="store_true", help="Emit JSON only")
    args = ap.parse_args()

    data_file = _resolve_data(args)

    strat_kwargs: dict = {}
    if args.params_file:
        strat_kwargs.update(json.load(open(args.params_file)))
    strat_kwargs["long_enabled"] = args.direction in ("long", "both")
    strat_kwargs["short_enabled"] = args.direction in ("short", "both")
    if args.no_atr_filter:
        strat_kwargs.update(
            long_use_atr_filter=False, long_use_atr_increment_filter=False,
            long_use_atr_decrement_filter=False, short_use_atr_filter=False,
            short_use_atr_increment_filter=False, short_use_atr_decrement_filter=False)

    strat, _ = run_backtest(data_file, strat_kwargs)
    report = build_report(strat)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("=" * 60)
    print("  CURRENT STRATEGY STATE (mechanical model — not advice)")
    print("=" * 60)
    print(f"  As of (UTC bar) : {report['as_of_utc']}")
    print(f"  Last close      : {report['last_close']}   ATR(10): {report['atr']}")
    print(f"  STATE           : {report['state']}"
          + (f"  ({report['direction']})" if report.get("direction") else ""))
    print(f"  ACTION          : {report['action']}")
    for key, label in (("entry_price", "Entry"), ("breakout_level", "Breakout level"),
                       ("window_top", "Window top"), ("window_bottom", "Window bottom"),
                       ("stop_loss", "Stop loss"), ("take_profit", "Take profit"),
                       ("prospective_stop_loss", "Prospective stop"),
                       ("prospective_take_profit", "Prospective target")):
        if report.get(key) is not None:
            print(f"  {label:<16}: {report[key]}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
