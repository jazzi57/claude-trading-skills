#!/usr/bin/env python3
"""Data sources for Gulf-market (DFM / ADX) swing screening.

Three sources, each returning daily OHLCV bars as a list of dicts
``{date, open, high, low, close, volume}`` (oldest first):

* ``YahooDFM``     -- DFM daily history (validated identical to the official
                      DFM feed). Yahoo does NOT cover ADX.
* ``ADXOfficial``  -- ADX snapshot + 52-week range via the public market-watch
                      API. Per-stock daily history is NOT exposed by ADX, so this
                      source returns a single-bar "snapshot" plus 52w levels.
* ``TwelveData``   -- vendor adapter (needs TWELVEDATA_API_KEY). Covers BOTH
                      DFM and ADX with full daily OHLCV.

All network helpers degrade gracefully: on error they return ``None`` / ``[]``
rather than raising, so a batch screen skips bad symbols instead of aborting.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Public market-watch key embedded in the ADX website's own frontend bundle;
# used here only to read the same delayed, public market data a browser sees.
_ADX_KEY = "1863a94c-582b-46f9-b4f0-0d02c0cc5307"
_ADX_GW = "https://apigateway.adx.ae"
_DFM_API = "https://api2.dfm.ae"


def _get_json(url: str, headers: dict | None = None, data: bytes | None = None,
              timeout: int = 20):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": _UA}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "ignore")
        return json.loads(body)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# DFM
# --------------------------------------------------------------------------- #
def dfm_universe(min_value: float = 300_000) -> list[dict]:
    """Return DFM main-board equities (market boards 510/200) that traded today.

    Each entry: ``{symbol, name, close, h52, l52, value}`` from the official
    ``/mw/v1/stocks`` feed.
    """
    rows = _get_json(f"{_DFM_API}/mw/v1/stocks",
                     headers={"User-Agent": _UA, "Accept": "application/json",
                              "Origin": "https://www.dfm.ae",
                              "Referer": "https://www.dfm.ae/"})
    out = []
    for r in rows or []:
        if str(r.get("market")) not in ("510", "200"):
            continue
        if (r.get("lastradeprice") or 0) <= 0:
            continue
        if (r.get("totalvalue") or 0) < min_value:
            continue
        out.append({
            "symbol": r["id"],
            "name": (r.get("name") or r["id"]).strip(),
            "close": r.get("closingprice") or 0,
            "h52": r.get("highestin52weeks") or 0,
            "l52": r.get("lowestin52weeks") or 0,
            "value": r.get("totalvalue") or 0,
        })
    return out


def yahoo_daily(symbol: str, yahoo_suffix: str = ".AE", rng: str = "1y") -> list[dict]:
    """Daily OHLCV bars for a DFM symbol via Yahoo (e.g. ``EMAAR`` -> ``EMAAR.AE``)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{symbol}{yahoo_suffix}?range={rng}&interval=1d")
    d = _get_json(url)
    try:
        r = d["chart"]["result"][0]
        ts = r["timestamp"]
        q = r["indicators"]["quote"][0]
    except Exception:
        return []
    bars = []
    for i, t in enumerate(ts):
        o, h, l, c, v = (q["open"][i], q["high"][i], q["low"][i],
                         q["close"][i], q["volume"][i])
        if None in (o, h, l, c):
            continue
        bars.append({"date": time.strftime("%Y-%m-%d", time.gmtime(t)),
                     "open": o, "high": h, "low": l, "close": c, "volume": v or 0})
    return bars


# --------------------------------------------------------------------------- #
# ADX
# --------------------------------------------------------------------------- #
def _adx_headers() -> dict:
    return {"User-Agent": _UA, "Accept": "application/json",
            "adx-Gateway-APIKey": _ADX_KEY, "Channel-ID": "OSS WEB",
            "Origin": "https://www.adx.ae", "Referer": "https://www.adx.ae/"}


def adx_main_board() -> list[str]:
    """Return ADX main-market security symbols."""
    d = _get_json(f"{_ADX_GW}/adx/marketwatch-delayed/1.1/securityBoards/mainMarket",
                  headers=_adx_headers())
    try:
        return [r["companySymbol"] for r in d["response"]["results"]]
    except Exception:
        return []


def adx_overview(symbol: str) -> dict | None:
    """Snapshot + 52-week range for one ADX symbol (no daily history available)."""
    d = _get_json(f"{_ADX_GW}/adx/marketwatch-delayed/1.1/securityOverview/{symbol}",
                  headers=_adx_headers())
    try:
        return d["response"]["overview"]
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Twelve Data (vendor) -- covers DFM and ADX with full daily history
# --------------------------------------------------------------------------- #
# Yahoo/Twelve Data style mic/exchange suffixes.
TWELVE_SUFFIX = {"dfm": "", "adx": ""}  # symbol+exchange passed explicitly below


def twelvedata_daily(symbol: str, exchange: str, api_key: str | None = None,
                     outputsize: int = 300) -> list[dict]:
    """Daily OHLCV via Twelve Data for ``exchange`` in {'DFM','ADX'}.

    Requires ``TWELVEDATA_API_KEY`` (env) or ``api_key``.
    """
    api_key = api_key or os.environ.get("TWELVEDATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVEDATA_API_KEY not set")
    qs = urllib.parse.urlencode({
        "symbol": symbol, "exchange": exchange, "interval": "1day",
        "outputsize": outputsize, "order": "ASC", "apikey": api_key,
    })
    d = _get_json(f"https://api.twelvedata.com/time_series?{qs}")
    if not d or d.get("status") == "error" or "values" not in d:
        return []
    bars = []
    for v in d["values"]:
        try:
            bars.append({"date": v["datetime"][:10],
                         "open": float(v["open"]), "high": float(v["high"]),
                         "low": float(v["low"]), "close": float(v["close"]),
                         "volume": float(v.get("volume") or 0)})
        except Exception:
            continue
    return bars
