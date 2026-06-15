#!/usr/bin/env python3
"""Run a Gulf-market (DFM / ADX) swing screen and write a report.

Examples
--------
  # DFM, full main board, true-ATR via Yahoo (validated vs official feed)
  python3 run_screen.py --market dfm --source yahoo --account 20000 --risk 1.0

  # ADX, 52-week-aware via the official snapshot feed (no daily history exists)
  python3 run_screen.py --market adx --source adx-official --account 20000

  # Either market with full daily history via Twelve Data (needs the key)
  TWELVEDATA_API_KEY=... python3 run_screen.py --market adx --source twelvedata
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_sources as ds           # noqa: E402
import swing_screen as ss           # noqa: E402


def _rows_dfm_yahoo(args):
    uni = ds.dfm_universe()
    print(f"DFM universe (official feed): {len(uni)} traded names", file=sys.stderr)
    rows = []
    for u in uni:
        bars = ds.yahoo_daily(u["symbol"], ".AE", rng="1y")
        time.sleep(0.1)
        res = ss.screen_from_bars(bars, args.account, args.risk, args.max_pos)
        res.update(symbol=u["symbol"], name=u["name"],
                   value_m=round(u["value"] / 1e6, 1))
        rows.append(res)
    return rows


def _rows_twelvedata(args, exchange):
    if exchange == "DFM":
        uni = ds.dfm_universe()
        syms = [(u["symbol"], u["name"], u["value"] / 1e6) for u in uni]
    else:
        syms = [(s, s, 0) for s in ds.adx_main_board()]
    print(f"{exchange} universe: {len(syms)} names (Twelve Data)", file=sys.stderr)
    rows = []
    for sym, name, val in syms:
        bars = ds.twelvedata_daily(sym, exchange, args.api_key)
        time.sleep(0.1)
        res = ss.screen_from_bars(bars, args.account, args.risk, args.max_pos)
        res.update(symbol=sym, name=name, value_m=round(val, 1))
        rows.append(res)
    return rows


def _rows_adx_official(args):
    syms = ds.adx_main_board()
    print(f"ADX main board: {len(syms)} names (official snapshot + 52w)", file=sys.stderr)
    rows = []
    for sym in syms:
        o = ds.adx_overview(sym)
        time.sleep(0.05)
        if not o:
            rows.append({"candidate": False, "reason": "no overview", "symbol": sym})
            continue
        res = ss.screen_from_snapshot(
            close=o.get("last") or 0, prev_close=o.get("previousClose") or 0,
            high=o.get("high") or 0, low=o.get("low") or 0,
            h52=o.get("52weekHigh") or 0, l52=o.get("52weekLow") or 0,
            change_pct=o.get("change") or 0,
            account=args.account, risk_pct=args.risk, max_pos_pct=args.max_pos)
        res.update(symbol=sym, name=o.get("companyID", sym),
                   value_m=round((o.get("value") or 0) / 1e6, 1))
        rows.append(res)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--market", choices=["dfm", "adx"], required=True)
    ap.add_argument("--source", choices=["yahoo", "adx-official", "twelvedata"],
                    required=True)
    ap.add_argument("--account", type=float, default=20000)
    ap.add_argument("--risk", type=float, default=1.0, help="risk %% per trade")
    ap.add_argument("--max-pos", type=float, default=20.0, help="max %% of account per position")
    ap.add_argument("--api-key", default=os.environ.get("TWELVEDATA_API_KEY"))
    ap.add_argument("--output-dir", default="reports")
    args = ap.parse_args()

    if args.source == "yahoo" and args.market == "dfm":
        rows = _rows_dfm_yahoo(args)
    elif args.source == "adx-official" and args.market == "adx":
        rows = _rows_adx_official(args)
    elif args.source == "twelvedata":
        rows = _rows_twelvedata(args, args.market.upper())
    else:
        ap.error(f"unsupported combination: --market {args.market} --source {args.source} "
                 f"(yahoo has no ADX coverage; adx-official is ADX-only)")

    cands = sorted([r for r in rows if r.get("candidate")],
                   key=lambda r: -r.get("value_m", 0))
    today = dt.date.today().isoformat()
    os.makedirs(args.output_dir, exist_ok=True)
    base = os.path.join(args.output_dir, f"{args.market}_swing_{today}")

    with open(base + ".json", "w") as f:
        json.dump({"market": args.market, "source": args.source, "date": today,
                   "account": args.account, "risk_pct": args.risk,
                   "candidates": cands, "all": rows}, f, indent=2)

    lines = [f"# {args.market.upper()} Swing Screen ({args.source})",
             f"**Date:** {today}  |  **Account:** {int(args.account):,}  "
             f"|  **Risk:** {args.risk}%/trade  |  **Candidates:** {len(cands)}", "",
             "| Ticker | BUY @ | Target | Stop | Shares | Cost | Risk | Method | Liq(M) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in cands:
        lines.append(f"| {r['symbol']} | {r['entry']} | {r['target']} | {r['stop']} | "
                     f"{r['shares']} | {r['cost']:.0f} | {r['risk']} | "
                     f"{r.get('method','')} | {r.get('value_m','')} |")
    md = "\n".join(lines) + "\n"
    with open(base + ".md", "w") as f:
        f.write(md)

    print(md)
    print(f"Saved: {base}.md / .json", file=sys.stderr)


if __name__ == "__main__":
    main()
