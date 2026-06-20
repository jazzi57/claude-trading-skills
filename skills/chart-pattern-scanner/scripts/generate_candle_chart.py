"""Generate a clean candlestick chart image for pattern scanning.

Mirrors ChartScanAI's chart-generation step: produce a candlestick PNG that the
vision-based scan (documented in SKILL.md) or a human can read. Data comes from
either a local OHLCV CSV (no network, no API key) or, when available, yfinance.

Heavy plotting dependencies (mplfinance / matplotlib) and yfinance are imported
lazily and guarded so the rest of the skill works without them. The pure-data
path (loading + validation) is shared with detect_candlestick_patterns.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

# Reuse the validated CSV loader from the sibling detector module.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_candlestick_patterns import Candle, load_ohlcv  # noqa: E402


def _candles_from_yfinance(ticker: str, period: str, interval: str) -> list:
    """Fetch OHLCV via yfinance. Raises RuntimeError with guidance if missing."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "yfinance is not installed. Install it (`pip install yfinance`) or "
            "supply data with --csv instead."
        ) from exc

    df = yf.Ticker(ticker).history(period=period, interval=interval)
    if df is None or df.empty:
        raise RuntimeError(f"No data returned for ticker '{ticker}'.")

    candles: list = []
    for idx, row in df.iterrows():
        candles.append(
            Candle(
                date=str(idx.date()) if hasattr(idx, "date") else str(idx),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0) or 0),
            )
        )
    return candles


def render_chart(candles: list, out_path: str, title: str) -> str:
    """Render candles to a PNG at out_path. Returns the path.

    Prefers mplfinance; falls back to a hand-drawn matplotlib candlestick.
    Raises RuntimeError if no plotting backend is available.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    # Preferred: mplfinance (requires pandas).
    try:
        import mplfinance as mpf
        import pandas as pd

        df = pd.DataFrame(
            {
                "Open": [c.open for c in candles],
                "High": [c.high for c in candles],
                "Low": [c.low for c in candles],
                "Close": [c.close for c in candles],
                "Volume": [c.volume for c in candles],
            },
            index=pd.to_datetime([c.date for c in candles], errors="coerce"),
        )
        mpf.plot(
            df,
            type="candle",
            style="charles",
            volume=True,
            title=title,
            savefig=dict(fname=out_path, dpi=120, bbox_inches="tight"),
        )
        return out_path
    except ImportError:
        pass

    # Fallback: draw candles manually with matplotlib.
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "Neither mplfinance nor matplotlib is installed. Install one "
            "(`pip install mplfinance` recommended) to render charts."
        ) from exc

    fig, ax = plt.subplots(figsize=(12, 6))
    for x, c in enumerate(candles):
        color = "#26a69a" if c.close >= c.open else "#ef5350"
        ax.plot([x, x], [c.low, c.high], color=color, linewidth=0.8, zorder=1)
        lower = min(c.open, c.close)
        height = max(abs(c.close - c.open), 1e-9)
        ax.add_patch(
            plt.Rectangle((x - 0.3, lower), 0.6, height, facecolor=color, edgecolor=color, zorder=2)
        )
    ax.set_title(title)
    ax.set_xlabel("Candle")
    ax.set_ylabel("Price")
    ax.margins(x=0.01)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a candlestick chart image.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--csv", help="Path to OHLCV CSV file")
    src.add_argument("--ticker", help="Ticker symbol to fetch via yfinance")
    parser.add_argument("--period", default="6mo", help="yfinance period (default: 6mo)")
    parser.add_argument("--interval", default="1d", help="yfinance interval (default: 1d)")
    parser.add_argument(
        "--output-dir", default="reports", help="Directory for the PNG (default: reports/)"
    )
    parser.add_argument("--title", default=None, help="Chart title override")
    args = parser.parse_args(argv)

    try:
        if args.ticker:
            candles = _candles_from_yfinance(args.ticker, args.period, args.interval)
            label = args.ticker.upper()
        else:
            candles = load_ohlcv(args.csv)
            label = os.path.splitext(os.path.basename(args.csv))[0].upper()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = os.path.join(args.output_dir, f"{label}_candles_{date}.png")
    title = args.title or f"{label} Candlestick Chart ({date})"

    try:
        render_chart(candles, out_path, title)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
