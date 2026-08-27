"""Generate a small synthetic XAUUSD 5-minute OHLCV CSV.

The original project ships a ~20 MB, 5-year gold dataset that is too large to
vendor into this repository. This script produces a compact, deterministic
substitute in the exact same column layout so the strategy runs end-to-end
out of the box:

    Date,Time,Open,High,Low,Close,Volume   (Date=%Y%m%d, Time=%H:%M:%S)

The output is a synthetic random walk, NOT real market data. Use it only to
verify the pipeline runs. For meaningful results, supply a real feed via
`--data /path/to/your.csv` when running sunrise_ogle_xauusd.py.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path


def generate(out_path: Path, days: int, start: str, seed: int,
             start_price: float) -> int:
    rng = random.Random(seed)
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    price = start_price
    rows = 0
    bar = timedelta(minutes=5)

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Date", "Time", "Open", "High", "Low", "Close", "Volume"])
        for day in range(days):
            day_dt = start_dt + timedelta(days=day)
            # Skip weekends (the gold market is closed Sat/Sun).
            if day_dt.weekday() >= 5:
                continue
            # 24h of 5-minute bars = 288 bars per day.
            ts = day_dt.replace(hour=0, minute=0, second=0)
            for _ in range(288):
                # Gentle drift + intraday sinusoidal component + noise.
                drift = math.sin(rows / 90.0) * 0.15
                step = rng.gauss(drift, 1.1)
                open_p = price
                close_p = max(1.0, open_p + step)
                high_p = max(open_p, close_p) + abs(rng.gauss(0, 0.6))
                low_p = min(open_p, close_p) - abs(rng.gauss(0, 0.6))
                volume = rng.randint(80_000, 420_000)
                writer.writerow([
                    ts.strftime("%Y%m%d"),
                    ts.strftime("%H:%M:%S"),
                    f"{open_p:.2f}", f"{high_p:.2f}",
                    f"{low_p:.2f}", f"{close_p:.2f}", volume,
                ])
                price = close_p
                ts += bar
                rows += 1
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent
                                         / "data" / "XAUUSD_5m_sample.csv"),
                    help="Output CSV path")
    ap.add_argument("--days", type=int, default=120,
                    help="Calendar days to span (weekends skipped)")
    ap.add_argument("--start", default="2024-01-01", help="First day YYYY-MM-DD")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (deterministic)")
    ap.add_argument("--start-price", type=float, default=2000.0,
                    help="Opening gold price")
    args = ap.parse_args()

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = generate(out_path, args.days, args.start, args.seed, args.start_price)
    print(f"Wrote {n} bars to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
