"""Tests for DFM daily price-limit helpers."""

import pytest
from daily_limit import (
    cap_target,
    daily_band,
    reachable_in_one_day,
    sessions_to_reach,
)


def test_daily_band():
    lo, hi = daily_band(100.0)
    assert lo == 85.0
    assert hi == 115.0


def test_daily_band_custom_pct():
    lo, hi = daily_band(100.0, pct=0.05)
    assert (lo, hi) == (95.0, 105.0)


def test_daily_band_bad():
    with pytest.raises(ValueError):
        daily_band(0)


def test_reachable_in_one_day():
    assert reachable_in_one_day(100, 114) is True
    assert reachable_in_one_day(100, 116) is False
    assert reachable_in_one_day(100, 86) is True
    assert reachable_in_one_day(100, 80) is False


def test_sessions_to_reach_within_one_day():
    assert sessions_to_reach(100, 110) == 1
    assert sessions_to_reach(100, 100) == 1


def test_sessions_to_reach_up_multi_day():
    # +40% needs: 1.15^1=1.15, ^2=1.32, ^3=1.52 -> 3 sessions
    assert sessions_to_reach(100, 140) == 3


def test_sessions_to_reach_down_multi_day():
    # 0.85^3=0.614 (>0.60), 0.85^4=0.522 (<0.60) -> 4 sessions to reach 60
    assert sessions_to_reach(100, 60) == 4


def test_cap_target_up_beyond_band():
    res = cap_target(100, 140)
    assert res["reachable_today"] is False
    assert res["one_day_capped"] == 115.0  # clamped to today's upper band
    assert res["sessions"] == 3


def test_cap_target_within_band():
    res = cap_target(100, 112)
    assert res["reachable_today"] is True
    assert res["one_day_capped"] == 112
    assert res["sessions"] == 1


def test_cap_target_down():
    res = cap_target(100, 70)
    assert res["one_day_capped"] == 85.0  # clamped to lower band
    assert res["reachable_today"] is False
