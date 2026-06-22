"""DFM daily price-limit (circuit band) helpers.

DFM caps how far an ordinary share can move in one session — the standard band is
±15% off the reference price (previous close). A signal's stop/target is only
realistic if it respects this: a 2R target that implies a >15% one-day move
simply cannot fill today; it needs multiple sessions.

These helpers compute the daily band, whether a level is reachable in one session,
and the minimum number of sessions a move needs under the compounding cap.

Note: a few securities trade on tighter/different bands (today NIH printed exactly
-5%); the public feed does not expose the per-stock limit, so callers pass the
pct (default 0.15) and should treat it as an assumption.
"""

from __future__ import annotations

import math

DEFAULT_LIMIT = 0.15


def daily_band(reference: float, pct: float = DEFAULT_LIMIT) -> tuple:
    """Return (lower, upper) price bounds reachable in one session."""
    if reference <= 0:
        raise ValueError("reference price must be positive")
    return (round(reference * (1 - pct), 4), round(reference * (1 + pct), 4))


def reachable_in_one_day(reference: float, target: float, pct: float = DEFAULT_LIMIT) -> bool:
    """True if `target` is within one session's ± band of `reference`."""
    lo, hi = daily_band(reference, pct)
    return lo <= target <= hi


def sessions_to_reach(reference: float, target: float, pct: float = DEFAULT_LIMIT) -> int:
    """Minimum sessions to move from reference to target under the daily cap.

    Compounds the ± limit per day. Returns 1 if already within one day's band
    (or if target == reference). Raises ValueError on non-positive prices.
    """
    if reference <= 0 or target <= 0:
        raise ValueError("prices must be positive")
    if reachable_in_one_day(reference, target, pct):
        return 1
    ratio = target / reference
    step = math.log(1 + pct) if target > reference else math.log(1 - pct)
    return max(1, math.ceil(math.log(ratio) / step))


def cap_target(reference: float, target: float, pct: float = DEFAULT_LIMIT) -> dict:
    """Annotate a target with daily-limit reality.

    Returns {target, one_day_capped, sessions, reachable_today} where
    one_day_capped clamps the target to today's band for a single-session plan.
    """
    lo, hi = daily_band(reference, pct)
    if target >= reference:
        capped = min(target, hi)
    else:
        capped = max(target, lo)
    return {
        "target": target,
        "one_day_capped": round(capped, 4),
        "sessions": sessions_to_reach(reference, target, pct),
        "reachable_today": reachable_in_one_day(reference, target, pct),
        "band": (lo, hi),
    }
