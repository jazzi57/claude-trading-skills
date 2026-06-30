"""One-command DFM market scan: refresh official data -> scan -> report.

Chains the three building blocks of the chart-pattern-scanner skill:
  1. fetch_dfm_official.fetch_series  -> official daily OHLC for the whole market
  2. detect_candlestick_patterns.scan -> BUY/SELL/NEUTRAL per symbol
  3. (optional) generate_candle_chart  -> a PNG per actionable name

Outputs a consolidated markdown report + per-symbol JSON to --output-dir.

The data/scan/report logic is split into pure functions (scan_series,
sort_rows, render_report_md) that are unit-tested offline; only fetch_series
touches the network.

Usage:
    python3 scan_dfm_market.py --from 2026-01-01 --to 2026-06-19 \
        --output-dir reports/dfm_official/
    python3 scan_dfm_market.py --from 2026-03-01 --to 2026-06-19 \
        --charts --min-bars 20 --output-dir reports/dfm_official/
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

# Sibling modules in the same scripts/ directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_candlestick_patterns import Candle, scan  # noqa: E402
from fetch_dfm_official import _parse_date, fetch_series, scrape_config  # noqa: E402

SIGNAL_ORDER = {"BUY": 0, "SELL": 1}


# --------------------------------------------------------------------------- #
# Pure logic (offline-testable)
# --------------------------------------------------------------------------- #
def _bars_to_candles(bars: list) -> list:
    """Convert stored bar dicts to Candle objects (accepts 'volume' or 'vol')."""
    out = []
    for b in bars:
        out.append(
            Candle(
                date=b["date"],
                open=float(b["open"]),
                high=float(b["high"]),
                low=float(b["low"]),
                close=float(b["close"]),
                volume=float(b.get("volume", b.get("vol", 0)) or 0),
            )
        )
    return out


def scan_series(series: dict, min_bars: int = 20, lookback: int = 3) -> list:
    """Run the detector over every symbol; return a list of result rows.

    Each row: {symbol, last, signal, score, confidence, latest_pattern, bars,
    result}. Symbols with fewer than `min_bars` bars are marked NODATA.
    """
    rows = []
    for sym, bars in series.items():
        if len(bars) < min_bars:
            rows.append(
                {
                    "symbol": sym,
                    "last": round(float(bars[-1]["close"]), 4) if bars else None,
                    "signal": "NODATA",
                    "score": 0.0,
                    "confidence": "none",
                    "latest_pattern": f"only {len(bars)} bars",
                    "bars": len(bars),
                    "result": None,
                }
            )
            continue
        candles = _bars_to_candles(bars)
        res = scan(candles, lookback=lookback)
        latest = f"{res.patterns[-1].name} @{res.patterns[-1].date}" if res.patterns else "-"
        rows.append(
            {
                "symbol": sym,
                "last": round(candles[-1].close, 4),
                "signal": res.signal,
                "score": res.score,
                "confidence": res.confidence,
                "latest_pattern": latest,
                "bars": len(bars),
                "result": res,
            }
        )
    return rows


def sort_rows(rows: list) -> list:
    """BUY first, then SELL (by descending |score|), then the rest."""
    return sorted(rows, key=lambda r: (SIGNAL_ORDER.get(r["signal"], 2), -abs(r["score"])))


def render_report_md(rows: list, as_of: str, source_note: str) -> str:
    """Render the consolidated market-scan markdown report."""
    rows = sort_rows(rows)
    buys = [r for r in rows if r["signal"] == "BUY"]
    sells = [r for r in rows if r["signal"] == "SELL"]
    others = [r for r in rows if r["signal"] not in ("BUY", "SELL")]
    scanned = [r for r in rows if r["signal"] != "NODATA"]

    out = []
    out.append("# DFM Market-Wide Candlestick Scan\n")
    out.append(f"**Date:** {as_of}  ")
    out.append(f"**Source:** {source_note}  ")
    out.append(f"**Universe:** {len(scanned)} scanned ({len(rows)} symbols total)\n")
    out.append(f"**Tally:** BUY {len(buys)} · SELL {len(sells)} · NEUTRAL/none {len(others)}\n")

    out.append("## Actionable signals\n")
    if buys or sells:
        out.append("| Ticker | Last | Signal | Score | Conf | Latest pattern |")
        out.append("|---|---|---|---|---|---|")
        for r in buys + sells:
            out.append(
                f"| {r['symbol']} | {r['last']} | **{r['signal']}** | "
                f"{r['score']:.2f} | {r['confidence']} | {r['latest_pattern']} |"
            )
    else:
        out.append("_No actionable BUY/SELL signals on the latest bar._")
    out.append("")

    neutral = [r for r in others if r["signal"] == "NEUTRAL"]
    if neutral:
        out.append("## Neutral / no decisive latest-bar pattern\n")
        out.append(", ".join(f"{r['symbol']}({r['last']})" for r in neutral))
        out.append("")

    out.append(
        "\n> Signal reflects candlestick patterns completing on the most recent bar; "
        "treat as triggers needing confirmation, not confirmed reversals.\n"
    )
    out.append(
        "*Informational/educational only — not financial advice. "
        "DFM widget API omits share volume (trade-count proxy).*"
    )
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Orchestration (network + IO)
# --------------------------------------------------------------------------- #
def _write_outputs(rows, series, output_dir, as_of, source_note):
    from detect_candlestick_patterns import _result_to_dict

    os.makedirs(output_dir, exist_ok=True)
    scans_dir = os.path.join(output_dir, "scans")
    os.makedirs(scans_dir, exist_ok=True)
    for r in rows:
        if r["result"] is not None:
            with open(os.path.join(scans_dir, f"{r['symbol']}_scan_{as_of}.json"), "w") as fh:
                json.dump(_result_to_dict(r["result"], r["symbol"]), fh, indent=2)
    report_path = os.path.join(output_dir, f"DFM_market_scan_{as_of}.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(render_report_md(rows, as_of, source_note))
    return report_path


def _render_charts(rows, series, output_dir):
    """Render charts for actionable names; returns count rendered."""
    try:
        from generate_candle_chart import render_chart
    except ImportError:
        return 0
    charts_dir = os.path.join(output_dir, "charts")
    n = 0
    for r in rows:
        if r["signal"] not in ("BUY", "SELL"):
            continue
        candles = _bars_to_candles(series[r["symbol"]][-90:])
        path = os.path.join(charts_dir, f"{r['symbol']}_candles.png")
        try:
            render_chart(candles, path, f"{r['symbol']} (DFM official) — last 90 sessions")
            n += 1
        except RuntimeError:
            return n  # no plotting backend; stop trying
    return n


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="One-command DFM refresh + scan + report.")
    p.add_argument("--from", dest="start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--to", dest="end", required=True, help="End date YYYY-MM-DD")
    p.add_argument("--output-dir", default="reports/dfm_official", help="Output directory")
    p.add_argument("--min-bars", type=int, default=20, help="Min bars to scan a symbol")
    p.add_argument("--lookback", type=int, default=3, help="Latest-bar lookback window")
    p.add_argument("--charts", action="store_true", help="Also render charts for signals")
    p.add_argument("--key", help="Override subscription key (default: scrape from dfm.ae)")
    p.add_argument("--pause", type=float, default=0.15, help="Seconds between requests")
    args = p.parse_args(argv)

    try:
        start, end = _parse_date(args.start), _parse_date(args.end)
    except ValueError as e:
        print(f"Error: bad date ({e})", file=sys.stderr)
        return 1

    try:
        api_base, key = scrape_config() if not args.key else (None, args.key)
        if args.key:
            from fetch_dfm_official import DEFAULT_API_BASE

            api_base = DEFAULT_API_BASE
    except (OSError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    def progress(i, n, d, nrows):
        print(f"  [{i}/{n}] {d} -> {nrows} securities", file=sys.stderr)

    print("Fetching official DFM data...", file=sys.stderr)
    series = fetch_series(start, end, api_base, key, pause=args.pause, progress=progress)
    if not series:
        print("Error: no data returned", file=sys.stderr)
        return 1

    rows = scan_series(series, min_bars=args.min_bars, lookback=args.lookback)
    as_of = dt.date.today().isoformat()
    source = f"Official DFM API (api2.dfm.ae), {args.start}..{args.end}"
    report_path = _write_outputs(rows, series, args.output_dir, as_of, source)

    buys = sum(1 for r in rows if r["signal"] == "BUY")
    sells = sum(1 for r in rows if r["signal"] == "SELL")
    print(
        f"Scanned {sum(1 for r in rows if r['signal'] != 'NODATA')} symbols: "
        f"BUY {buys} · SELL {sells}"
    )
    print(f"Report: {report_path}")

    if args.charts:
        n = _render_charts(rows, series, args.output_dir)
        print(f"Charts rendered: {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
