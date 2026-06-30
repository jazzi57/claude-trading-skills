"""Tests for DFM asymmetric daily price-limit helpers (-5% down / +15% up)."""

import pytest
from daily_limit import (
    DFM_DOWN,
    DFM_UP,
    cap_target,
    daily_band,
    reachable_in_one_day,
    sessions_to_reach,
)


def test_sessions_to_reach_guards_zero_and_full_caps():
    # a 0% cap in the needed direction -> unreachable, clean ValueError (not ZeroDivisionError)
    with pytest.raises(ValueError, match="unreachable"):
        sessions_to_reach(100.0, 200.0, up_pct=0.0, down_pct=0.05)
    with pytest.raises(ValueError, match="unreachable"):
        sessions_to_reach(100.0, 50.0, up_pct=0.15, down_pct=0.0)
    # down_pct >= 1 implies a non-positive price -> ValueError (not math domain error)
    with pytest.raises(ValueError, match="down_pct"):
        sessions_to_reach(100.0, 50.0, up_pct=0.15, down_pct=1.0)


def test_defaults_are_asymmetric():
    assert DFM_UP == 0.15
    assert DFM_DOWN == 0.05


def test_daily_band_asymmetric():
    lo, hi = daily_band(100.0)
    assert lo == 95.0  # -5% down
    assert hi == 115.0  # +15% up


def test_daily_band_bad():
    with pytest.raises(ValueError):
        daily_band(0)


def test_reachable_in_one_day():
    assert reachable_in_one_day(100, 114) is True  # +14% within +15%
    assert reachable_in_one_day(100, 116) is False  # beyond +15%
    assert reachable_in_one_day(100, 95.5) is True  # -4.5% within -5%
    assert reachable_in_one_day(100, 94) is False  # beyond -5%


def test_sessions_up_uses_15pct():
    # +40%: 1.15^3=1.52 -> 3 sessions
    assert sessions_to_reach(100, 140) == 3


def test_sessions_down_uses_5pct():
    # -10%: 0.95^2=.9025 (>0.90), 0.95^3=.857 (<0.90) -> 3 sessions to reach 90
    assert sessions_to_reach(100, 90) == 3


def test_sessions_down_is_slow():
    # -20% at only 5%/day: 0.95^n<=0.80 -> 5 sessions (vs ~2 under a 15% cap)
    assert sessions_to_reach(100, 80) == 5


def test_cap_target_short_beyond_daily_floor():
    # short from 3.60 to 3.12 (-13.3%) under -5% cap
    res = cap_target(3.60, 3.12)
    assert res["reachable_today"] is False
    assert res["one_day_capped"] == 3.42  # today's -5% floor
    assert res["sessions"] == 3


def test_cap_target_within_band():
    res = cap_target(100, 112)
    assert res["reachable_today"] is True
    assert res["sessions"] == 1
