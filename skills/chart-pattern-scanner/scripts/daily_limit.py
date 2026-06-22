"""DFM daily price-limit (circuit band) helpers — asymmetric.

DFM caps how far an ordinary share moves in one session. Since ~March 2026 the
band is **asymmetric**: up to **+15%** but only **-5%** on the downside (the
downward limit was tightened to curb sharp declines; confirmed in the data —
sub-5% down days effectively vanish from 2026-03 onward, while +15% up days
persist). Before that the band was ±15%.

A signal's stop/target is only realistic if it respects this. A short target
implying a >5% one-day fall cannot fill today; it needs multiple sessions.

Note: a few securities/boards may differ and the public feed does not expose the
per-stock limit, so the up/down pct are parameters (DFM defaults below) and
should be treated as assumptions.
"""

from __future__ import annotations

import math

# Current DFM regime (since ~2026-03).
DFM_UP = 0.15
DFM_DOWN = 0.05


def daily_band(reference: float, up_pct: float = DFM_UP, down_pct: float = DFM_DOWN) -> tuple:
    """Return (lower, upper) price bounds reachable in one session."""
    if reference <= 0:
        raise ValueError("reference price must be positive")
    return (round(reference * (1 - down_pct), 4), round(reference * (1 + up_pct), 4))


def reachable_in_one_day(
    reference: float, target: float, up_pct: float = DFM_UP, down_pct: float = DFM_DOWN
) -> bool:
    """True if `target` is within one session's band of `reference`."""
    lo, hi = daily_band(reference, up_pct, down_pct)
    return lo <= target <= hi


def sessions_to_reach(
    reference: float, target: float, up_pct: float = DFM_UP, down_pct: float = DFM_DOWN
) -> int:
    """Minimum sessions to move from reference to target under the daily cap.

    Uses the up cap for targets above reference and the (tighter) down cap below.
    Returns 1 if already within one session's band. Raises on non-positive prices.
    """
    if reference <= 0 or target <= 0:
        raise ValueError("prices must be positive")
    if reachable_in_one_day(reference, target, up_pct, down_pct):
        return 1
    ratio = target / reference
    step = math.log(1 + up_pct) if target > reference else math.log(1 - down_pct)
    return max(1, math.ceil(math.log(ratio) / step))


def cap_target(
    reference: float, target: float, up_pct: float = DFM_UP, down_pct: float = DFM_DOWN
) -> dict:
    """Annotate a target with daily-limit reality.

    Returns {target, one_day_capped, sessions, reachable_today, band}.
    one_day_capped clamps the target to today's band for a single-session plan.
    """
    lo, hi = daily_band(reference, up_pct, down_pct)
    capped = min(target, hi) if target >= reference else max(target, lo)
    return {
        "target": target,
        "one_day_capped": round(capped, 4),
        "sessions": sessions_to_reach(reference, target, up_pct, down_pct),
        "reachable_today": reachable_in_one_day(reference, target, up_pct, down_pct),
        "band": (lo, hi),
    }
