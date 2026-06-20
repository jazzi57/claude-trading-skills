"""Fetch official Dubai Financial Market (DFM) daily OHLC data.

Data source: the public DFM website backend (`api2.dfm.ae`), the same
`SearchCompanyPrices` widget endpoint the official "Historical Data" page uses.
Calling it once per trading day with an empty company filter returns the whole
market's OHLC for that day; iterating a date range reconstructs a clean daily
candlestick series per symbol that feeds `detect_candlestick_patterns.py`.

The Azure APIM subscription key is a *public* client-side key embedded in the
DFM website; this script scrapes it at runtime (so it keeps working if DFM
rotates it) rather than hardcoding it. Network functions are thin; the parsing
and series-building logic is pure and unit-tested offline.

Usage:
    python3 fetch_dfm_official.py --from 2026-01-01 --to 2026-06-19 \
        --output-dir reports/dfm_official/
    python3 fetch_dfm_official.py --from 2026-05-01 --to 2026-06-19 \
        --symbols EMAAR,SALIK,DIC --output-dir reports/dfm_official/
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

DFM_HOME = "https://www.dfm.ae/"
DEFAULT_API_BASE = "https://api2.dfm.ae/web/widgets/v1"
KEY_RE = re.compile(r'ocpApimSubscriptionKey:"([0-9a-fA-F]{16,})"')
APIBASE_RE = re.compile(r'apiBaseUrl:"(https://[^"]+)"')


# --------------------------------------------------------------------------- #
# Pure, offline-testable logic
# --------------------------------------------------------------------------- #
def iter_trading_days(start: dt.date, end: dt.date) -> list:
    """Return weekdays (Mon-Fri) in [start, end]; DFM's trading week.

    Public holidays are not modelled — non-trading days simply return no rows
    from the API and are skipped during ingestion.
    """
    if end < start:
        raise ValueError("end date must be on or after start date")
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def parse_day_response(payload: dict) -> list:
    """Flatten a SearchCompanyPrices response into a list of security rows.

    Each row is normalised to {symbol, open, high, low, close, trade_count}.
    Rows with non-numeric or non-positive close are dropped.
    """
    rows = []
    for sector in payload.get("sectors", []) or []:
        for s in sector.get("securities", []) or []:
            try:
                o = float(s["open"])
                h = float(s["high"])
                low = float(s["low"])
                c = float(s["close"])
            except (KeyError, TypeError, ValueError):
                continue
            if c <= 0:
                continue
            rows.append(
                {
                    "symbol": s.get("symbol"),
                    "open": o,
                    "high": h,
                    "low": low,
                    "close": c,
                    "trade_count": float(s.get("trade_count") or 0),
                }
            )
    return rows


def add_day_to_series(series: dict, date: dt.date, rows: list) -> None:
    """Append each row to series[symbol] with the bar date (in place)."""
    iso = date.isoformat()
    for r in rows:
        sym = r["symbol"]
        if not sym:
            continue
        series.setdefault(sym, []).append(
            {
                "date": iso,
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["trade_count"],
            }
        )


def build_form_body(date: dt.date, companies: str = "") -> bytes:
    """URL-encoded POST body for a single-day SearchCompanyPrices request."""
    params = {
        "Command": "SearchCompanyPrices",
        "Period": "custom",
        "FromDate": date.strftime("%d/%m/%Y"),
        "ToDate": date.strftime("%d/%m/%Y"),
        "Companies": companies,
        "Language": "en",
        "type": "json",
    }
    return urllib.parse.urlencode(params).encode()


def write_csvs(series: dict, output_dir: str, symbols: list | None = None) -> list:
    """Write one OHLCV CSV per symbol. Returns the list of paths written."""
    os.makedirs(output_dir, exist_ok=True)
    written = []
    for sym, bars in series.items():
        if symbols and sym not in symbols:
            continue
        if not bars:
            continue
        path = os.path.join(output_dir, f"{sym}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
            for b in bars:
                w.writerow(
                    [b["date"], b["open"], b["high"], b["low"], b["close"], int(b["volume"])]
                )
        written.append(path)
    return written


# --------------------------------------------------------------------------- #
# Network layer (thin)
# --------------------------------------------------------------------------- #
def _http_get(url: str, headers: dict, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def scrape_config() -> tuple:
    """Fetch the public API base URL and subscription key from the DFM site."""
    html = _http_get(DFM_HOME, {"User-Agent": "Mozilla/5.0"})
    key_m = KEY_RE.search(html)
    if not key_m:
        raise RuntimeError(
            "Could not locate the DFM API subscription key on dfm.ae — the site "
            "layout may have changed. Pass --key explicitly."
        )
    base_m = APIBASE_RE.search(html)
    api_base = base_m.group(1) if base_m else DEFAULT_API_BASE
    return api_base, key_m.group(1)


def fetch_day(
    date: dt.date, api_base: str, key: str, companies: str = "", retries: int = 3
) -> dict:
    """POST a single-day SearchCompanyPrices request; returns parsed JSON or {}."""
    url = api_base.rstrip("/") + "/data"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Ocp-Apim-Subscription-Key": key,
        "Referer": DFM_HOME,
    }
    body = build_form_body(date, companies)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001 — network resilience; retry then give up
            if attempt == retries - 1:
                return {}
            time.sleep(1.5 * (attempt + 1))
    return {}


def fetch_series(
    start: dt.date,
    end: dt.date,
    api_base: str,
    key: str,
    companies: str = "",
    pause: float = 0.15,
    progress=None,
) -> dict:
    """Fetch and assemble a daily series per symbol over [start, end]."""
    series: dict = {}
    days = iter_trading_days(start, end)
    for i, d in enumerate(days, 1):
        payload = fetch_day(d, api_base, key, companies)
        rows = parse_day_response(payload)
        add_day_to_series(series, d, rows)
        if progress:
            progress(i, len(days), d, len(rows))
        time.sleep(pause)
    return series


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Fetch official DFM daily OHLC data.")
    p.add_argument("--from", dest="start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--to", dest="end", required=True, help="End date YYYY-MM-DD")
    p.add_argument("--symbols", help="Comma-separated symbols to write (default: all)")
    p.add_argument("--output-dir", default="reports/dfm_official", help="CSV output directory")
    p.add_argument("--key", help="Override subscription key (default: scrape from dfm.ae)")
    p.add_argument("--api-base", default=None, help="Override API base URL")
    p.add_argument("--pause", type=float, default=0.15, help="Seconds between requests")
    p.add_argument("--series-json", action="store_true", help="Also dump combined series JSON")
    args = p.parse_args(argv)

    try:
        start, end = _parse_date(args.start), _parse_date(args.end)
    except ValueError as e:
        print(f"Error: bad date ({e})", file=sys.stderr)
        return 1

    if args.key:
        api_base = args.api_base or DEFAULT_API_BASE
        key = args.key
    else:
        try:
            scraped_base, key = scrape_config()
            api_base = args.api_base or scraped_base
        except (OSError, RuntimeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    def progress(i, n, d, nrows):
        print(f"  [{i}/{n}] {d} -> {nrows} securities", file=sys.stderr)

    series = fetch_series(start, end, api_base, key, pause=args.pause, progress=progress)
    if not series:
        print("Error: no data returned (check dates / connectivity)", file=sys.stderr)
        return 1

    paths = write_csvs(series, args.output_dir, symbols)
    print(f"Wrote {len(paths)} CSV files to {args.output_dir} ({len(series)} symbols total)")

    if args.series_json:
        os.makedirs(args.output_dir, exist_ok=True)
        jpath = os.path.join(args.output_dir, "_all_series.json")
        with open(jpath, "w", encoding="utf-8") as fh:
            json.dump(series, fh)
        print(f"Wrote combined series JSON to {jpath}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
