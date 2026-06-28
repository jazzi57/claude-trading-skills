"""Fetch real gold (XAU/USD) 5-minute OHLCV data for the strategy.

Writes a CSV in the exact layout the strategy expects:

    Date,Time,Open,High,Low,Close,Volume   (Date=%Y%m%d, Time=%H:%M:%S, UTC)

Two keyless/keyed sources are supported:

  * ``yahoo`` (default, no API key) — Yahoo Finance public chart endpoint.
    Intraday 5-minute history is capped by Yahoo at ~60 days lookback.
    Default symbol ``GC=F`` (COMEX front-month gold futures).

  * ``fmp`` (needs ``FMP_API_KEY``) — Financial Modeling Prep intraday
    historical-chart endpoint. Default symbol ``XAUUSD``. FMP serves a longer
    intraday history than Yahoo on paid tiers.

Both use ``requests`` (which trusts the environment's CA bundle), so neither
depends on yfinance's curl_cffi backend.

Examples
--------
    python fetch_data.py                              # GC=F, last 60d, via Yahoo
    python fetch_data.py --range 30d                  # last 30 days
    python fetch_data.py --symbol XAUUSD=X            # Yahoo spot gold (no volume)
    python fetch_data.py --source fmp --symbol XAUUSD # FMP (FMP_API_KEY required)

Then backtest:
    python sunrise_ogle_xauusd.py --data data/GC=F_5m.csv --quiet
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FMP_CHART = "https://financialmodelingprep.com/api/v3/historical-chart/5min/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; backtrader-pullback/1.0)"}

# Row = (epoch_seconds_utc, open, high, low, close, volume)
Row = tuple


def _get_json(url: str, params: dict, retries: int = 4) -> dict:
    """GET with exponential backoff; raises on persistent failure."""
    delay = 2.0
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            # 429/5xx are worth retrying; 4xx (except 429) are not.
            if resp.status_code != 429 and 400 <= resp.status_code < 500:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            last_err = RuntimeError(f"HTTP {resp.status_code}")
        except requests.RequestException as exc:
            last_err = exc
        if attempt < retries - 1:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"Request failed after {retries} attempts: {last_err}")


def fetch_yahoo(symbol: str, rng: str) -> list[Row]:
    data = _get_json(YAHOO_CHART.format(symbol=symbol),
                     {"interval": "5m", "range": rng, "includePrePost": "false"})
    chart = data.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(f"Yahoo error for {symbol}: {chart['error']}")
    results = chart.get("result")
    if not results:
        raise RuntimeError(f"Yahoo returned no data for {symbol}")
    res = results[0]
    stamps = res.get("timestamp") or []
    quote = res["indicators"]["quote"][0]
    o, h, l, c = quote["open"], quote["high"], quote["low"], quote["close"]
    v = quote.get("volume") or [None] * len(stamps)
    rows: list[Row] = []
    for i, ts in enumerate(stamps):
        # Skip bars Yahoo hasn't fully populated (forming candle / gaps).
        if None in (o[i], h[i], l[i], c[i]):
            continue
        rows.append((ts, o[i], h[i], l[i], c[i], v[i] or 0))
    return rows


def fetch_fmp(symbol: str, api_key: str) -> list[Row]:
    data = _get_json(FMP_CHART.format(symbol=symbol), {"apikey": api_key})
    if isinstance(data, dict) and data.get("Error Message"):
        raise RuntimeError(f"FMP error: {data['Error Message']}")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"FMP returned no data for {symbol}")
    rows: list[Row] = []
    for bar in data:
        try:
            # FMP 'date' is naive exchange-local "YYYY-MM-DD HH:MM:SS"; treat as UTC.
            dt = datetime.strptime(bar["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append((int(dt.timestamp()), bar["open"], bar["high"],
                         bar["low"], bar["close"], bar.get("volume", 0) or 0))
        except (KeyError, ValueError):
            continue
    rows.sort(key=lambda r: r[0])  # FMP returns newest-first
    return rows


def write_csv(rows: list[Row], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Date", "Time", "Open", "High", "Low", "Close", "Volume"])
        for ts, o, h, l, c, vol in rows:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            writer.writerow([dt.strftime("%Y%m%d"), dt.strftime("%H:%M:%S"),
                             f"{o:.2f}", f"{h:.2f}", f"{l:.2f}", f"{c:.2f}", int(vol)])
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["yahoo", "fmp"], default="yahoo",
                    help="Data provider (default: yahoo, no API key)")
    ap.add_argument("--symbol", default=None,
                    help="Ticker (default: GC=F for yahoo, XAUUSD for fmp)")
    ap.add_argument("--range", default="60d",
                    help="Yahoo lookback window, max ~60d for 5m bars")
    ap.add_argument("--fmp-api-key", default=os.environ.get("FMP_API_KEY"),
                    help="FMP API key (or set FMP_API_KEY)")
    ap.add_argument("--out", default=None, help="Output CSV path")
    args = ap.parse_args()

    symbol = args.symbol or ("GC=F" if args.source == "yahoo" else "XAUUSD")
    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent / "data"
        / f"{symbol.replace('=', '').replace('/', '')}_5m.csv")

    try:
        if args.source == "yahoo":
            rows = fetch_yahoo(symbol, args.range)
        else:
            if not args.fmp_api_key:
                print("ERROR: --source fmp requires --fmp-api-key or FMP_API_KEY",
                      file=sys.stderr)
                return 1
            rows = fetch_fmp(symbol, args.fmp_api_key)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("ERROR: no usable bars returned", file=sys.stderr)
        return 1

    n = write_csv(rows, out_path.resolve())
    first = datetime.fromtimestamp(rows[0][0], tz=timezone.utc)
    last = datetime.fromtimestamp(rows[-1][0], tz=timezone.utc)
    print(f"Wrote {n} bars ({symbol}, {args.source}) "
          f"{first:%Y-%m-%d %H:%M} -> {last:%Y-%m-%d %H:%M} UTC")
    print(f"  {out_path.resolve()}")
    print(f"Backtest it:\n  python sunrise_ogle_xauusd.py --data {out_path} --quiet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
