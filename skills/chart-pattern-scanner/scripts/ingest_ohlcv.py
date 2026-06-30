"""Ingest an arbitrary OHLCV export (iVestor / broker / Excel / CSV) into the
series JSON format used by backtest_patterns.py and scan_dfm_market.py.

Handles:
- CSV and (if openpyxl is installed) .xlsx
- single-symbol files (symbol from a column, --symbol, or the filename) and
  multi-symbol files (a Symbol/Ticker/Code column)
- flexible, case-insensitive column names (English + a few Arabic aliases)
- mixed date formats (ISO, DD/MM/YYYY, MM/DD/YYYY)

Output: {symbol: [ {date, open, high, low, close, volume}, ... ]} sorted ascending,
written to <output-dir>/_all_series.json — then run backtest_patterns.py on it.

Pure parsing logic is unit-tested offline.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

# canonical field -> accepted header aliases (lowercased).
# Order within a list is the preference order when a file carries two matching
# columns (e.g. the DFM bulletin has both current_close and last_price -> close;
# current_close, the daily settlement, is listed first so it wins).
ALIASES = {
    "date": [
        "date", "datetime", "time", "trade date", "tradedate",
        "report_date", "day", "تاريخ", "اليوم",
    ],
    "open": ["open", "o", "openprice", "open price", "افتتاح"],
    "high": ["high", "h", "highprice", "high price", "اعلى", "أعلى"],
    "low": ["low", "l", "lowprice", "low price", "ادنى", "أدنى"],
    "close": [
        "close", "current_close", "c", "closeprice", "close price",
        "last_price", "last", "ltp", "اغلاق", "إغلاق",
    ],
    "volume": ["volume", "trade_volume", "vol", "qty", "quantity", "shares", "حجم", "الكمية"],
    "symbol": ["symbol", "ticker", "code", "company", "security", "name", "الرمز", "الشركة"],
}

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y"]


def normalize_header(name: str) -> str | None:
    """Map a raw header to a canonical field name, or None if unrecognized."""
    key = (name or "").strip().lower()
    for canon, al in ALIASES.items():
        if key in al:
            return canon
    return None


def detect_columns(headers: list) -> dict:
    """Return {canonical: index} for recognized columns.

    When a file carries two columns mapping to the same canonical field, the
    column whose header is the more-preferred alias (earlier in its ALIASES
    list) wins — so the DFM bulletin's current_close beats last_price for
    `close`. Ties on alias rank fall back to header position.
    """
    best: dict = {}  # canon -> (alias_rank, header_index)
    out: dict = {}
    for i, h in enumerate(headers):
        canon = normalize_header(h)
        if not canon:
            continue
        rank = ALIASES[canon].index((h or "").strip().lower())
        if canon not in best or (rank, i) < best[canon]:
            best[canon] = (rank, i)
            out[canon] = i
    return out


def parse_date(s: str) -> str:
    """Parse a date string to ISO (YYYY-MM-DD). Raises ValueError if none match."""
    s = (s or "").strip()
    # strip a time component if present
    s = s.split("T")[0].split(" ")[0] if ("T" in s or (" " in s and ":" in s)) else s
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {s!r}")


def parse_rows(headers: list, rows: list, default_symbol: str | None = None) -> list:
    """Parse raw rows into (symbol, bar) records using detected columns."""
    cols = detect_columns(headers)
    missing = [f for f in ("open", "high", "low", "close") if f not in cols]
    if missing:
        raise ValueError(f"missing required columns: {', '.join(missing)}")
    if "date" not in cols:
        raise ValueError("missing required 'date' column")
    has_sym = "symbol" in cols

    records = []
    for r in rows:
        if not r:
            continue
        # Coerce cells to strings up front (None -> "") so a caller passing
        # pre-typed rows (numbers, None) is handled like the CSV/XLSX readers,
        # which already stringify — every .strip()/float() below stays safe.
        r = ["" if c is None else str(c) for c in r]
        if all(c.strip() == "" for c in r):
            continue
        try:
            sym = (r[cols["symbol"]].strip() if has_sym else (default_symbol or "")).upper()
            if not sym:
                raise ValueError("no symbol (provide --symbol or a Symbol column)")
            bar = {
                "date": parse_date(r[cols["date"]]),
                "open": float(r[cols["open"]]),
                "high": float(r[cols["high"]]),
                "low": float(r[cols["low"]]),
                "close": float(r[cols["close"]]),
                "volume": float(r[cols["volume"]])
                if "volume" in cols and r[cols["volume"]].strip()
                else 0.0,
            }
        except (IndexError, ValueError) as e:
            raise ValueError(f"bad row {r}: {e}") from e
        # Drop untraded sessions: the DFM bulletin carries O=H=L=0 (sometimes
        # with a carried-forward close) on days a symbol didn't trade. Require a
        # real OHLC bar.
        if bar["open"] > 0 and bar["high"] > 0 and bar["low"] > 0 and bar["close"] > 0:
            records.append((sym, bar))
    return records


def build_series(records: list) -> dict:
    """Group (symbol, bar) records into {symbol: [bars sorted by date]}, deduped."""
    series: dict = {}
    seen: dict = {}
    for sym, bar in records:
        key = (sym, bar["date"])
        if key in seen:
            continue
        seen[key] = True
        series.setdefault(sym, []).append(bar)
    for sym in series:
        series[sym].sort(key=lambda b: b["date"])
    return series


# --------------------------------------------------------------------------- #
# File readers
# --------------------------------------------------------------------------- #
def read_csv(path: str) -> tuple:
    import csv

    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = list(csv.reader(fh))
    if not reader:
        raise ValueError(f"empty file: {path}")
    return reader[0], reader[1:]


def read_xlsx(path: str) -> tuple:
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError(
            "openpyxl is required for .xlsx files (`pip install openpyxl`), "
            "or export as CSV instead."
        ) from e
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]
    if not rows:
        raise ValueError(f"empty sheet: {path}")
    return rows[0], rows[1:]


def read_file(path: str) -> tuple:
    if path.lower().endswith((".xlsx", ".xlsm")):
        return read_xlsx(path)
    return read_csv(path)


def ingest(paths: list, default_symbol: str | None = None) -> dict:
    """Ingest one or more files into a merged series dict."""
    all_records = []
    for p in paths:
        headers, rows = read_file(p)
        sym = default_symbol or os.path.splitext(os.path.basename(p))[0]
        all_records.extend(parse_rows(headers, rows, default_symbol=sym))
    return build_series(all_records)


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Ingest OHLCV export(s) into series JSON.")
    p.add_argument("inputs", nargs="+", help="CSV/XLSX file(s) or a directory")
    p.add_argument("--symbol", help="Symbol for single-symbol files lacking a Symbol column")
    p.add_argument("--output-dir", default="reports/dfm_history", help="Where to write series JSON")
    args = p.parse_args(argv)

    # expand directories
    files = []
    for inp in args.inputs:
        if os.path.isdir(inp):
            for fn in sorted(os.listdir(inp)):
                if fn.lower().endswith((".csv", ".xlsx", ".xlsm")):
                    files.append(os.path.join(inp, fn))
        else:
            files.append(inp)
    if not files:
        print("Error: no input files found", file=sys.stderr)
        return 1

    try:
        series = ingest(files, default_symbol=args.symbol)
    except (OSError, ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    os.makedirs(args.output_dir, exist_ok=True)
    out = os.path.join(args.output_dir, "_all_series.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(series, fh)
    nbars = sum(len(v) for v in series.values())
    spans = [f"{s}:{v[0]['date']}→{v[-1]['date']}({len(v)})" for s, v in list(series.items())[:5]]
    print(f"Ingested {len(series)} symbols, {nbars} bars -> {out}")
    print("Sample:", "; ".join(spans))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
