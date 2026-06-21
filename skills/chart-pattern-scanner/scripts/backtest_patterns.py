"""Backtest candlestick patterns on historical OHLCV to get empirical hit-rates.

Turns the deterministic detector's patterns into *data-backed* probabilities:
for every pattern occurrence across a universe of symbols, measure the forward
close-to-close outcome over one or more horizons, then aggregate into a hit-rate
and average forward return per pattern. Pooling across many symbols gives usable
sample sizes even when any single stock has few occurrences.

This replaces the heuristic "estimated probability" with an empirical one derived
from the market's own history.

Pure functions (forward_outcomes, aggregate_stats, summarize_pattern,
backtest_all) are unit-tested offline; the CLI loads a series JSON and writes a
report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_candlestick_patterns import Candle, detect_patterns  # noqa: E402

# Pattern -> directional bias used to score "hit".
PATTERN_DIRECTION = {
    "hammer": "bullish",
    "inverted_hammer": "bullish",
    "bullish_marubozu": "bullish",
    "bullish_engulfing": "bullish",
    "piercing_line": "bullish",
    "bullish_harami": "bullish",
    "tweezer_bottom": "bullish",
    "morning_star": "bullish",
    "three_white_soldiers": "bullish",
    "hanging_man": "bearish",
    "shooting_star": "bearish",
    "bearish_marubozu": "bearish",
    "bearish_engulfing": "bearish",
    "dark_cloud_cover": "bearish",
    "bearish_harami": "bearish",
    "tweezer_top": "bearish",
    "evening_star": "bearish",
    "three_black_crows": "bearish",
    # doji / spinning_top are neutral -> skipped
}


def forward_outcomes(candles: list, idx: int, horizon: int) -> dict | None:
    """Close-to-close outcome `horizon` bars after the event at `idx`.

    Returns {fwd_return, up} or None if there aren't enough forward bars.
    """
    if idx + horizon >= len(candles):
        return None
    c0 = candles[idx].close
    c1 = candles[idx + horizon].close
    if c0 <= 0:
        return None
    ret = (c1 - c0) / c0
    return {"fwd_return": ret, "up": c1 > c0}


def aggregate_stats(outcomes: list, direction: str) -> dict:
    """Aggregate outcomes into n, hit_rate, avg_return, median-ish stats.

    "hit" = move in the pattern's expected direction (bullish -> up, bearish -> down).
    """
    n = len(outcomes)
    if n == 0:
        return {"n": 0, "hit_rate": None, "avg_return": None, "avg_return_dir": None}
    if direction == "bullish":
        hits = sum(1 for o in outcomes if o["up"])
    else:
        hits = sum(1 for o in outcomes if not o["up"])
    avg_ret = sum(o["fwd_return"] for o in outcomes) / n
    # average return in the trade's direction (bearish profits on down moves)
    sign = 1 if direction == "bullish" else -1
    avg_dir = sum(sign * o["fwd_return"] for o in outcomes) / n
    return {
        "n": n,
        "hit_rate": hits / n,
        "avg_return": avg_ret,
        "avg_return_dir": avg_dir,
    }


def summarize_pattern(series: dict, pattern_name: str, direction: str, horizons=(5, 10)) -> dict:
    """Collect forward outcomes for one pattern across all symbols, per horizon."""
    by_h = {h: [] for h in horizons}
    for _sym, candles in series.items():
        if len(candles) < max(horizons) + 2:
            continue
        hits = [h for h in detect_patterns(candles) if h.name == pattern_name]
        for hit in hits:
            for h in horizons:
                out = forward_outcomes(candles, hit.index, h)
                if out is not None:
                    by_h[h].append(out)
    return {h: aggregate_stats(by_h[h], direction) for h in horizons}


def backtest_all(series: dict, horizons=(5, 10)) -> dict:
    """Backtest every known directional pattern. Returns {pattern: {horizon: stats}}."""
    results = {}
    for name, direction in PATTERN_DIRECTION.items():
        results[name] = {
            "direction": direction,
            "horizons": summarize_pattern(series, name, direction, horizons),
        }
    return results


# --------------------------------------------------------------------------- #
# IO / CLI
# --------------------------------------------------------------------------- #
def _load_series_json(path: str) -> dict:
    """Load a series JSON (symbol -> list of bar dicts) into Candle lists."""
    raw = json.load(open(path, encoding="utf-8"))
    series = {}
    for sym, bars in raw.items():
        series[sym] = [
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
    return series


def render_report(results: dict, horizons, meta: str) -> str:
    out = ["# Candlestick Pattern Backtest — Empirical Hit-Rates\n", f"{meta}\n"]
    out.append("Hit = forward close moved in the pattern's expected direction.\n")
    for direction in ("bullish", "bearish"):
        out.append(f"## {direction.title()} patterns\n")
        out.append(
            "| Pattern | "
            + " | ".join(f"n@{h}d | hit@{h}d | avgDirRet@{h}d" for h in horizons)
            + " |"
        )
        out.append("|---" * (1 + 3 * len(horizons)) + "|")
        rows = [(n, v) for n, v in results.items() if v["direction"] == direction]
        # sort by hit rate at first horizon (desc), Nones last
        h0 = horizons[0]
        rows.sort(key=lambda kv: kv[1]["horizons"][h0]["hit_rate"] or -1, reverse=True)
        for name, v in rows:
            cells = []
            for h in horizons:
                s = v["horizons"][h]
                if s["n"]:
                    cells += [
                        str(s["n"]),
                        f"{s['hit_rate'] * 100:.0f}%",
                        f"{s['avg_return_dir'] * 100:+.1f}%",
                    ]
                else:
                    cells += ["0", "—", "—"]
            out.append(f"| {name} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Backtest candlestick patterns on a series JSON.")
    p.add_argument("--series-json", required=True, help="Path to series JSON (symbol -> bars)")
    p.add_argument("--horizons", default="5,10", help="Comma-separated forward horizons in days")
    p.add_argument("--output-dir", default="reports", help="Where to write the report/JSON")
    args = p.parse_args(argv)

    horizons = tuple(int(x) for x in args.horizons.split(","))
    try:
        series = _load_series_json(args.series_json)
    except (OSError, ValueError, KeyError) as e:
        print(f"Error loading series: {e}", file=sys.stderr)
        return 1

    results = backtest_all(series, horizons)
    nbars = sum(len(v) for v in series.values())
    meta = f"**Universe:** {len(series)} symbols, {nbars} bars · horizons {horizons}"
    os.makedirs(args.output_dir, exist_ok=True)
    md = render_report(results, horizons, meta)
    md_path = os.path.join(args.output_dir, "DFM_pattern_backtest.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    json_path = os.path.join(args.output_dir, "DFM_pattern_backtest.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"Wrote {md_path} and {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
