"""Deterministic candlestick pattern detector.

Rule-based cross-check for the chart-pattern-scanner skill. Reads OHLCV data
from a CSV file (or accepts an in-memory list of candles) and detects classic
single-, double-, and triple-candle patterns, then aggregates the most recent
detections into a BUY / SELL / NEUTRAL signal.

This is the deterministic counterpart to the vision-based scan documented in
SKILL.md. It uses only the Python standard library (csv) so it runs anywhere
without pandas/numpy/mplfinance installed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Candle:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        """Absolute size of the real body."""
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        """Full high-to-low range."""
        return self.high - self.low

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def midpoint(self) -> float:
        return (self.open + self.close) / 2.0


# Each detector returns a list of these.
@dataclass
class PatternHit:
    name: str
    signal: str  # "bullish" | "bearish" | "neutral"
    reliability: float  # 0.0 - 1.0 prior reliability weight
    index: int  # index of the LAST candle forming the pattern
    date: str
    note: str = ""


@dataclass
class ScanResult:
    patterns: list = field(default_factory=list)
    signal: str = "NEUTRAL"
    score: float = 0.0
    confidence: str = "low"
    rationale: str = ""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _is_doji(c: Candle, body_frac: float = 0.1) -> bool:
    if c.range <= 0:
        return False
    return c.body <= body_frac * c.range


def _trend_before(candles: list, idx: int, window: int = 5) -> str:
    """Classify the short-term trend leading INTO candle idx (exclusive).

    Uses the slope of closes over the preceding `window` candles.
    Returns "up", "down", or "flat".
    """
    start = max(0, idx - window)
    closes = [c.close for c in candles[start:idx]]
    if len(closes) < 2:
        return "flat"
    first, last = closes[0], closes[-1]
    if first == 0:
        return "flat"
    change = (last - first) / abs(first)
    if change > 0.01:
        return "up"
    if change < -0.01:
        return "down"
    return "flat"


# --------------------------------------------------------------------------- #
# Single-candle detectors
# --------------------------------------------------------------------------- #
def _detect_single(candles: list, i: int) -> list:
    c = candles[i]
    hits: list = []
    if c.range <= 0:
        return hits
    trend = _trend_before(candles, i)

    body_frac = c.body / c.range
    upper = c.upper_shadow
    lower = c.lower_shadow

    # Doji - indecision
    if _is_doji(c):
        hits.append(PatternHit("doji", "neutral", 0.3, i, c.date, "Small body; indecision"))

    # Hammer / Hanging Man: long lower shadow, small upper shadow, small body
    if lower >= 2 * c.body and upper <= 0.15 * c.range and body_frac < 0.4 and c.body > 0:
        if trend == "down":
            hits.append(
                PatternHit("hammer", "bullish", 0.6, i, c.date, "Long lower shadow after downtrend")
            )
        elif trend == "up":
            hits.append(
                PatternHit(
                    "hanging_man", "bearish", 0.5, i, c.date, "Long lower shadow after uptrend"
                )
            )

    # Inverted Hammer / Shooting Star: long upper shadow, small lower shadow
    if upper >= 2 * c.body and lower <= 0.15 * c.range and body_frac < 0.4 and c.body > 0:
        if trend == "down":
            hits.append(
                PatternHit(
                    "inverted_hammer",
                    "bullish",
                    0.5,
                    i,
                    c.date,
                    "Long upper shadow after downtrend",
                )
            )
        elif trend == "up":
            hits.append(
                PatternHit(
                    "shooting_star", "bearish", 0.6, i, c.date, "Long upper shadow after uptrend"
                )
            )

    # Marubozu: very large body, negligible shadows
    if body_frac >= 0.9:
        if c.is_bullish:
            hits.append(
                PatternHit("bullish_marubozu", "bullish", 0.55, i, c.date, "Full-body up candle")
            )
        elif c.is_bearish:
            hits.append(
                PatternHit("bearish_marubozu", "bearish", 0.55, i, c.date, "Full-body down candle")
            )

    return hits


# --------------------------------------------------------------------------- #
# Double-candle detectors
# --------------------------------------------------------------------------- #
def _detect_double(candles: list, i: int) -> list:
    if i < 1:
        return []
    prev, c = candles[i - 1], candles[i]
    hits: list = []
    trend = _trend_before(candles, i - 1)

    # Bullish Engulfing
    if (
        prev.is_bearish
        and c.is_bullish
        and c.close >= prev.open
        and c.open <= prev.close
        and c.body > prev.body
    ):
        hits.append(
            PatternHit(
                "bullish_engulfing",
                "bullish",
                0.7,
                i,
                c.date,
                "Up candle engulfs prior down candle",
            )
        )

    # Bearish Engulfing
    if (
        prev.is_bullish
        and c.is_bearish
        and c.open >= prev.close
        and c.close <= prev.open
        and c.body > prev.body
    ):
        hits.append(
            PatternHit(
                "bearish_engulfing",
                "bearish",
                0.7,
                i,
                c.date,
                "Down candle engulfs prior up candle",
            )
        )

    # Piercing Line (bullish): prior bearish, current opens below prior low, closes above prior midpoint
    if (
        trend == "down"
        and prev.is_bearish
        and c.is_bullish
        and c.open < prev.low
        and prev.midpoint < c.close < prev.open
    ):
        hits.append(
            PatternHit("piercing_line", "bullish", 0.6, i, c.date, "Closes above prior midpoint")
        )

    # Dark Cloud Cover (bearish)
    if (
        trend == "up"
        and prev.is_bullish
        and c.is_bearish
        and c.open > prev.high
        and prev.open < c.close < prev.midpoint
    ):
        hits.append(
            PatternHit("dark_cloud_cover", "bearish", 0.6, i, c.date, "Closes below prior midpoint")
        )

    # Bullish Harami: large bearish then small bullish inside
    if (
        prev.is_bearish
        and c.is_bullish
        and c.open > prev.close
        and c.close < prev.open
        and c.body < prev.body
    ):
        hits.append(
            PatternHit("bullish_harami", "bullish", 0.45, i, c.date, "Small body inside prior body")
        )

    # Bearish Harami
    if (
        prev.is_bullish
        and c.is_bearish
        and c.open < prev.close
        and c.close > prev.open
        and c.body < prev.body
    ):
        hits.append(
            PatternHit("bearish_harami", "bearish", 0.45, i, c.date, "Small body inside prior body")
        )

    # Tweezer bottom / top: matching lows/highs
    if prev.range > 0 and c.range > 0:
        tol = 0.001 * max(c.close, 1.0)
        if trend == "down" and abs(prev.low - c.low) <= tol and prev.is_bearish and c.is_bullish:
            hits.append(PatternHit("tweezer_bottom", "bullish", 0.4, i, c.date, "Matching lows"))
        if trend == "up" and abs(prev.high - c.high) <= tol and prev.is_bullish and c.is_bearish:
            hits.append(PatternHit("tweezer_top", "bearish", 0.4, i, c.date, "Matching highs"))

    return hits


# --------------------------------------------------------------------------- #
# Triple-candle detectors
# --------------------------------------------------------------------------- #
def _detect_triple(candles: list, i: int) -> list:
    if i < 2:
        return []
    a, b, c = candles[i - 2], candles[i - 1], candles[i]
    hits: list = []
    trend = _trend_before(candles, i - 2)

    # Morning Star (bullish): big down, small body (gap down), big up closing into first body
    if (
        trend == "down"
        and a.is_bearish
        and b.body < a.body * 0.5
        and c.is_bullish
        and c.close > a.midpoint
    ):
        hits.append(
            PatternHit("morning_star", "bullish", 0.75, i, c.date, "3-candle bottom reversal")
        )

    # Evening Star (bearish)
    if (
        trend == "up"
        and a.is_bullish
        and b.body < a.body * 0.5
        and c.is_bearish
        and c.close < a.midpoint
    ):
        hits.append(PatternHit("evening_star", "bearish", 0.75, i, c.date, "3-candle top reversal"))

    # Three White Soldiers
    if (
        a.is_bullish
        and b.is_bullish
        and c.is_bullish
        and b.close > a.close
        and c.close > b.close
        and b.open > a.open
        and c.open > b.open
    ):
        hits.append(
            PatternHit("three_white_soldiers", "bullish", 0.7, i, c.date, "Three rising up candles")
        )

    # Three Black Crows
    if (
        a.is_bearish
        and b.is_bearish
        and c.is_bearish
        and b.close < a.close
        and c.close < b.close
        and b.open < a.open
        and c.open < b.open
    ):
        hits.append(
            PatternHit("three_black_crows", "bearish", 0.7, i, c.date, "Three falling down candles")
        )

    return hits


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def detect_patterns(candles: list) -> list:
    """Return every PatternHit found across the series."""
    hits: list = []
    for i in range(len(candles)):
        hits.extend(_detect_single(candles, i))
        hits.extend(_detect_double(candles, i))
        hits.extend(_detect_triple(candles, i))
    return hits


def _signed(hit: PatternHit) -> float:
    if hit.signal == "bullish":
        return hit.reliability
    if hit.signal == "bearish":
        return -hit.reliability
    return 0.0


def aggregate_signal(candles: list, hits: list, lookback: int = 3) -> ScanResult:
    """Aggregate pattern hits into a BUY / SELL / NEUTRAL signal.

    The signal is decisive on patterns that *complete on the most recent candle*
    (this is the "current bar" signal a scanner reports). When the latest candle
    carries no directional pattern, fall back to a recency-decayed sum over the
    preceding `lookback` candles so a recent-but-not-latest setup still surfaces.
    Older/conflicting patterns are always retained for context but never override
    a fresh completion on the last bar.
    """
    if not candles:
        return ScanResult(signal="NEUTRAL", confidence="none", rationale="No data")

    last_idx = len(candles) - 1
    last_hits = [h for h in hits if h.index == last_idx]
    last_directional = [h for h in last_hits if h.signal in ("bullish", "bearish")]

    if last_directional:
        score = sum(_signed(h) for h in last_directional)
        names = ", ".join(sorted({h.name for h in last_directional}))
        rationale = f"Latest candle: {names} (net {score:+.2f})"
    else:
        # Fall back to a recency-decayed window sum.
        cutoff = last_idx - (lookback - 1)
        window = [h for h in hits if h.index >= cutoff and h.signal in ("bullish", "bearish")]
        score = sum(_signed(h) * (0.5 ** (last_idx - h.index)) for h in window)
        if window:
            names = ", ".join(sorted({h.name for h in window}))
            rationale = (
                f"Recent setup (no pattern on latest bar): {names} (decayed net {score:+.2f})"
            )
        else:
            rationale = "No recognized patterns in the lookback window"

    if score >= 0.5:
        signal = "BUY"
    elif score <= -0.5:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    abs_score = abs(score)
    if abs_score >= 1.0:
        confidence = "high"
    elif abs_score >= 0.5:
        confidence = "medium"
    elif abs_score > 0:
        confidence = "low"
    else:
        confidence = "none"

    return ScanResult(
        patterns=hits,
        signal=signal,
        score=round(score, 3),
        confidence=confidence,
        rationale=rationale,
    )


def scan(candles: list, lookback: int = 3) -> ScanResult:
    hits = detect_patterns(candles)
    return aggregate_signal(candles, hits, lookback=lookback)


# --------------------------------------------------------------------------- #
# CSV loading
# --------------------------------------------------------------------------- #
def load_ohlcv(path: str) -> list:
    """Load OHLCV candles from a CSV file.

    Recognizes case-insensitive columns: date, open, high, low, close, volume.
    Accepts common aliases (e.g. 'Adj Close' ignored). Raises ValueError on
    missing required columns or malformed numeric data.
    """
    candles: list = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError("CSV file is empty")
        lower = {name.lower().strip(): name for name in reader.fieldnames}
        required = ["open", "high", "low", "close"]
        missing = [col for col in required if col not in lower]
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(missing)}")
        date_col = lower.get("date") or lower.get("datetime") or lower.get("timestamp")
        vol_col = lower.get("volume") or lower.get("vol")

        for row_num, row in enumerate(reader, start=2):
            try:
                candle = Candle(
                    date=(row[date_col].strip() if date_col else str(row_num)),
                    open=float(row[lower["open"]]),
                    high=float(row[lower["high"]]),
                    low=float(row[lower["low"]]),
                    close=float(row[lower["close"]]),
                    volume=float(row[vol_col]) if vol_col and row.get(vol_col) else 0.0,
                )
            except (ValueError, KeyError) as exc:
                raise ValueError(f"Malformed numeric data on row {row_num}: {exc}") from exc
            candles.append(candle)

    if not candles:
        raise ValueError("CSV contained no data rows")
    return candles


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _result_to_dict(result: ScanResult, ticker: str | None) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ticker": ticker,
        "signal": result.signal,
        "score": result.score,
        "confidence": result.confidence,
        "rationale": result.rationale,
        "patterns": [
            {
                "name": h.name,
                "signal": h.signal,
                "reliability": h.reliability,
                "index": h.index,
                "date": h.date,
                "note": h.note,
            }
            for h in result.patterns
        ],
    }


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic candlestick pattern detector (rule-based)."
    )
    parser.add_argument("--csv", required=True, help="Path to OHLCV CSV file")
    parser.add_argument("--ticker", help="Optional ticker label for the report")
    parser.add_argument(
        "--lookback",
        type=int,
        default=3,
        help="Number of most-recent candles to aggregate for the signal (default: 3)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="If set, also write a JSON report to this directory",
    )
    args = parser.parse_args(argv)

    try:
        candles = load_ohlcv(args.csv)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    result = scan(candles, lookback=args.lookback)
    payload = _result_to_dict(result, args.ticker)

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        label = (args.ticker or "chart").upper()
        out_path = os.path.join(args.output_dir, f"{label}_pattern_scan_{date}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"Wrote {out_path}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"=== Candlestick Pattern Scan {'(' + args.ticker + ')' if args.ticker else ''} ===")
        print(f"Signal:     {result.signal} ({result.confidence} confidence)")
        print(f"Score:      {result.score:+.2f}")
        print(f"Rationale:  {result.rationale}")
        if result.patterns:
            print("\nDetected patterns (chronological):")
            for h in result.patterns:
                print(f"  [{h.date}] {h.name:22s} {h.signal:8s} r={h.reliability:.2f}  {h.note}")
        else:
            print("\nNo recognized candlestick patterns.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
