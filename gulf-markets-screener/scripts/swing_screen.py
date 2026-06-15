#!/usr/bin/env python3
"""Swing-trade screening logic for Gulf-market equities.

Two screen modes share one trade-plan builder:

* ``screen_from_bars`` -- full daily history available (DFM via Yahoo/Twelve Data,
  ADX via Twelve Data). Uses a Minervini-style trend template + true 14-day ATR
  stop.
* ``screen_from_snapshot`` -- snapshot + 52-week range only (ADX official feed).
  Uses 52-week positioning as the trend/breakout proxy and a volatility-adaptive
  stop (session range, floored/capped), since no ATR series exists.

A "candidate" is a stock the screen thinks is biased to rise (confirmed uptrend
near a breakout). Everything else is reported as no-trade with a reason -- the
screen never invents a level for a stock that isn't set up.
"""
from __future__ import annotations

import math


def sma(values: list[float], n: int) -> float | None:
    return sum(values[-n:]) / n if len(values) >= n else None


def atr(highs, lows, closes, n: int = 14) -> float | None:
    """Wilder ATR over the last ``n`` true ranges."""
    if len(closes) <= n:
        return None
    trs = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    return a


def _plan(entry: float, stop: float, account: float, risk_pct: float,
          max_pos_pct: float) -> dict:
    """Risk-based trade plan: shares, cost, target (2R), capped by position size."""
    risk_per_share = entry - stop
    if risk_per_share <= 0:
        return {}
    target = entry + 2 * risk_per_share
    shares = math.floor((account * risk_pct / 100) / risk_per_share)
    cap = math.floor((account * max_pos_pct / 100) / entry)
    shares = min(shares, cap)
    if shares < 1:
        return {}
    return {
        "entry": round(entry, 3), "stop": round(stop, 3), "target": round(target, 3),
        "shares": shares, "cost": round(shares * entry, 0),
        "risk": round(shares * risk_per_share, 1),
        "r_multiple": 2.0,
    }


def screen_from_bars(bars: list[dict], account: float = 20000, risk_pct: float = 1.0,
                     max_pos_pct: float = 20.0, atr_mult: float = 2.0,
                     min_upside_pct: float = 10.0, min_headroom_pct: float = 4.0,
                     max_price: float | None = None) -> dict:
    """Trend-template + true-ATR screen on daily OHLCV bars (oldest first).

    Quality gate (the "is there money to be made?" mix):
      * ``min_upside_pct``   -- sell-target must be at least this %% above entry.
      * ``min_headroom_pct`` -- must have at least this %% room up to the 52-week
                                high (skip names pinned at their ceiling).
      * ``max_price``        -- optional: skip shares priced above this.
    """
    if len(bars) < 60:
        return {"candidate": False, "reason": "insufficient history"}
    o = [b["open"] for b in bars]
    h = [b["high"] for b in bars]
    lo = [b["low"] for b in bars]
    c = [b["close"] for b in bars]
    px = c[-1]
    a = atr(h, lo, c, 14)
    s50, s200 = sma(c, 50), sma(c, 200) or sma(c, 150)
    hi20, hi52 = max(h[-20:]), max(h)
    ret3m = (px / c[-63] - 1) * 100 if len(c) > 63 else (px / c[0] - 1) * 100
    if not a or a <= 0 or not s50 or not s200:
        return {"candidate": False, "reason": "indicators unavailable"}

    uptrend = px > s50 and px > s200 and s50 > s200
    near_breakout = px >= hi20 * 0.97
    new_high = px >= hi52 * 0.98
    if not uptrend:
        return {"candidate": False, "reason": "not in uptrend", "ret3m": round(ret3m, 1)}
    if not (near_breakout or new_high):
        return {"candidate": False, "reason": "not near breakout", "ret3m": round(ret3m, 1)}
    if max_price is not None and px > max_price:
        return {"candidate": False, "reason": f"price > {max_price}"}

    headroom = (hi52 - px) / px * 100
    if headroom < min_headroom_pct:
        return {"candidate": False, "reason": "at 52w ceiling (little room up)",
                "to_high_pct": round(headroom, 1)}

    entry = max(px, hi20) * 1.001
    plan = _plan(entry, entry - atr_mult * a, account, risk_pct, max_pos_pct)
    if not plan:
        return {"candidate": False, "reason": "position too small / risk too wide"}
    upside = (plan["target"] / plan["entry"] - 1) * 100
    if upside < min_upside_pct:
        return {"candidate": False, "reason": f"upside {upside:.0f}% < {min_upside_pct:.0f}%"}
    plan.update({"candidate": True, "price": round(px, 3), "atr": round(a, 3),
                 "ret3m": round(ret3m, 1), "upside_pct": round(upside, 1),
                 "to_high_pct": round(headroom, 1),
                 "ext_pct": round((px - hi20) / hi20 * 100, 1),
                 "method": "trend-template + true-ATR"})
    return plan


def screen_from_snapshot(close: float, prev_close: float, high: float, low: float,
                         h52: float, l52: float, change_pct: float,
                         account: float = 20000, risk_pct: float = 1.0,
                         max_pos_pct: float = 20.0, min_upside_pct: float = 10.0,
                         min_headroom_pct: float = 4.0,
                         max_price: float | None = None) -> dict:
    """52-week-positioning screen for snapshot-only data (ADX official feed)."""
    if close <= 0 or h52 <= 0 or l52 <= 0 or high <= 0:
        return {"candidate": False, "reason": "bad snapshot"}
    rng = h52 - l52
    pos52 = (close - l52) / rng if rng > 0 else 0
    near_high = close >= 0.85 * h52
    if not (near_high and pos52 >= 0.55 and change_pct >= -1):
        return {"candidate": False, "reason": "not near 52w high / not in uptrend",
                "pos52": round(pos52 * 100)}
    if max_price is not None and close > max_price:
        return {"candidate": False, "reason": f"price > {max_price}"}
    headroom = (h52 - close) / close * 100
    if headroom < min_headroom_pct:
        return {"candidate": False, "reason": "at 52w ceiling (little room up)",
                "to_high_pct": round(headroom, 1)}
    entry = max(high, close) * 1.001
    srng = (high - low) / close if close > 0 else 0.06
    stop_pct = min(max(srng, 0.05), 0.12)            # 5%..12% volatility-adaptive
    plan = _plan(entry, entry * (1 - stop_pct), account, risk_pct, max_pos_pct)
    if not plan:
        return {"candidate": False, "reason": "position too small"}
    upside = (plan["target"] / plan["entry"] - 1) * 100
    if upside < min_upside_pct:
        return {"candidate": False, "reason": f"upside {upside:.0f}% < {min_upside_pct:.0f}%"}
    plan.update({"candidate": True, "price": round(close, 3),
                 "pos52": round(pos52 * 100), "upside_pct": round(upside, 1),
                 "to_high_pct": round(headroom, 1),
                 "change_pct": round(change_pct, 1),
                 "method": "52w-positioning (snapshot)"})
    return plan
