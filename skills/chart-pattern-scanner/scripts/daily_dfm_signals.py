"""Daily DFM signal runner — turns the backtest's two surviving edges into a
single actionable report.

The DFM study (references/dfm_backtest_findings.md) found exactly two things
worth trading:

1. **EMAAR ~ EMAARDEV pair** — z-score of the log price ratio mean-reverts
   (81% win-rate in backtest). Report the current spread state.
2. **High-volume bearish reversals** — `hanging_man` / `shooting_star` only
   carry an edge when the event bar trades on above-average volume
   (hanging_man 64% vs 56% at 10d; shooting_star 55% vs 40%). Scan every
   symbol's most recent bar(s) for one.

Everything else (bullish/momentum candles) had no edge or mean-reverted against
its own direction, so it is deliberately *not* signalled here.

Run it against a freshly-ingested bulletin series; it prints a summary and
writes reports/DFM_daily_signals.{md,json}. Informational/educational only —
not financial advice, and mind the DFM retail short constraint.

Pure functions (recent_volume_reversals, scan_volume_reversals, pair_signals)
are unit-tested offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest_patterns import avg_prior_volume, volume_bucket  # noqa: E402
from detect_candlestick_patterns import Candle, detect_patterns  # noqa: E402
from pairs_strategy import current_pair_signal  # noqa: E402

# The only candlestick patterns the backtest found worth acting on, and only on
# high volume. Both bearish (short / lighten / exit triggers).
RELIABLE_VOLUME_PATTERNS = ("hanging_man", "shooting_star")

# The pair the correlation study + backtest flagged as the strongest edge.
DEFAULT_PAIRS = [("EMAAR", "EMAARDEV")]


def _to_candles(bars: list) -> list:
    return [
        Candle(
            b["date"],
            float(b["open"]),
            float(b["high"]),
            float(b["low"]),
            float(b["close"]),
            float(b.get("volume", b.get("vol", 0)) or 0),
        )
        for b in bars
    ]


def recent_volume_reversals(
    candles: list,
    patterns=RELIABLE_VOLUME_PATTERNS,
    lookback: int = 20,
    mult: float = 1.5,
    within: int = 1,
) -> list:
    """High-volume bearish-reversal hits within the last `within` bars.

    Returns [{pattern, date, bars_ago, volume_bucket, vol_ratio}] for hits whose
    event bar traded on high volume (>= mult x its prior `lookback`-bar average).
    """
    last = len(candles) - 1
    out = []
    for hit in detect_patterns(candles):
        if hit.name not in patterns:
            continue
        bars_ago = last - hit.index
        if bars_ago < 0 or bars_ago >= within:
            continue
        if volume_bucket(candles, hit.index, lookback, mult) != "high":
            continue
        base = avg_prior_volume(candles, hit.index, lookback)
        ratio = candles[hit.index].volume / base if base else None
        out.append(
            {
                "pattern": hit.name,
                "signal": hit.signal,
                "date": hit.date,
                "bars_ago": bars_ago,
                "volume_bucket": "high",
                "vol_ratio": round(ratio, 2) if ratio is not None else None,
            }
        )
    return out


def scan_volume_reversals(
    series: dict,
    patterns=RELIABLE_VOLUME_PATTERNS,
    lookback: int = 20,
    mult: float = 1.5,
    within: int = 1,
) -> list:
    """Run recent_volume_reversals across every symbol; flatten to rows."""
    rows = []
    for sym, bars in series.items():
        candles = bars if bars and isinstance(bars[0], Candle) else _to_candles(bars)
        if len(candles) < lookback + 3:
            continue
        for hit in recent_volume_reversals(candles, patterns, lookback, mult, within):
            rows.append({"symbol": sym, **hit})
    rows.sort(key=lambda r: (r["bars_ago"], -(r["vol_ratio"] or 0)))
    return rows


def pair_signals(series: dict, pairs=DEFAULT_PAIRS, lookback: int = 20, entry_z: float = 2.0) -> list:
    """Current spread signal for each configured pair present in the series."""
    out = []
    for a, b in pairs:
        if a not in series or b not in series:
            continue
        amap = {x["date"]: x["close"] for x in series[a] if x["close"] > 0}
        bmap = {x["date"]: x["close"] for x in series[b] if x["close"] > 0}
        dates = sorted(set(amap) & set(bmap))
        if len(dates) < lookback + 5:
            continue
        ac = [amap[d] for d in dates]
        bc = [bmap[d] for d in dates]
        sig = current_pair_signal(ac, bc, lookback, entry_z)
        out.append({"a": a, "b": b, "n": len(dates), **sig})
    return out


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def render_report(pairs_out: list, scan_rows: list, meta: str, within: int) -> str:
    out = ["# DFM Daily Signals\n", f"{meta}\n"]
    out.append(
        "Only the two edges that survived the DFM backtest are signalled: the "
        "EMAAR~EMAARDEV spread and **high-volume** hanging_man / shooting_star "
        "reversals. Informational only — not financial advice; mind the DFM "
        "retail short constraint.\n"
    )

    out.append("## Pair spreads (relative value)\n")
    if pairs_out:
        out.append("| Pair | z | ratio | signal |")
        out.append("|---|---|---|---|")
        for p in pairs_out:
            out.append(f"| {p['a']}~{p['b']} | {p.get('z')} | {p.get('ratio')} | {p['signal']} |")
    else:
        out.append("_No configured pair had enough overlapping history._")
    out.append("")

    out.append(f"## High-volume bearish reversals (last {within} bar(s))\n")
    if scan_rows:
        out.append("| Symbol | Pattern | Date | Bars ago | Vol vs avg |")
        out.append("|---|---|---|---|---|")
        for r in scan_rows:
            vr = f"{r['vol_ratio']}x" if r["vol_ratio"] is not None else "—"
            out.append(
                f"| {r['symbol']} | {r['pattern']} | {r['date']} | {r['bars_ago']} | {vr} |"
            )
    else:
        out.append("_No high-volume hanging_man / shooting_star in the window._")
    out.append("")
    return "\n".join(out)


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Daily DFM actionable-signal runner.")
    p.add_argument("--series-json", default="reports/dfm_bulletin/_all_series.json")
    p.add_argument("--output-dir", default="reports")
    p.add_argument("--lookback", type=int, default=20)
    p.add_argument("--mult", type=float, default=1.5, help="High-volume multiple of prior average")
    p.add_argument("--within", type=int, default=1, help="How many recent bars to scan for hits")
    p.add_argument("--entry-z", type=float, default=2.0)
    p.add_argument(
        "--pair", action="append", default=[],
        help="Extra pair as A:B (repeatable); defaults to EMAAR:EMAARDEV",
    )
    args = p.parse_args(argv)

    try:
        raw = json.load(open(args.series_json, encoding="utf-8"))
    except OSError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    pairs = DEFAULT_PAIRS + [tuple(x.split(":", 1)) for x in args.pair if ":" in x]
    pairs_out = pair_signals(raw, pairs, args.lookback, args.entry_z)
    scan_rows = scan_volume_reversals(
        raw, RELIABLE_VOLUME_PATTERNS, args.lookback, args.mult, args.within
    )

    meta = f"**Universe:** {len(raw)} symbols · lookback {args.lookback} · high≥{args.mult:g}×avg"
    os.makedirs(args.output_dir, exist_ok=True)
    md = render_report(pairs_out, scan_rows, meta, args.within)
    md_path = os.path.join(args.output_dir, "DFM_daily_signals.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    json_path = os.path.join(args.output_dir, "DFM_daily_signals.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({"pairs": pairs_out, "reversals": scan_rows}, fh, indent=2)

    print(f"=== DFM daily signals ({len(raw)} symbols) ===")
    for p_ in pairs_out:
        print(f"  pair {p_['a']}~{p_['b']}: z={p_.get('z')} -> {p_['signal']}")
    print(f"  high-volume reversals (last {args.within} bar(s)): {len(scan_rows)}")
    for r in scan_rows[:10]:
        print(f"    {r['symbol']:13s} {r['pattern']:14s} {r['date']} ({r['vol_ratio']}x vol)")
    print(f"Wrote {md_path} and {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
