"""Unit tests for the swing-screen logic (pure functions, no network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swing_screen as ss  # noqa: E402


def _trend_bars(n=260, start=8.0, step=0.001):
    """Synthetic series rising/falling gently by ``step``/day, closing near highs.

    A small step keeps prices realistic (no exponential blow-up) so position
    sizing behaves like it would on a real low-priced Gulf-market name.
    """
    bars = []
    price = start
    for i in range(n):
        o = price
        price = price * (1 + step)
        c = price
        hi = max(o, c) * 1.003
        lo = min(o, c) * 0.997
        bars.append({"date": f"d{i}", "open": o, "high": hi,
                     "low": lo, "close": c, "volume": 1000})
    return bars


def _uptrend_bars(n=260):
    return _trend_bars(n, start=8.0, step=0.001)


def test_atr_positive_on_trending_series():
    bars = _uptrend_bars()
    a = ss.atr([b["high"] for b in bars], [b["low"] for b in bars],
               [b["close"] for b in bars], 14)
    assert a and a > 0


def test_uptrend_breakout_is_candidate_with_2r_target():
    # relax the upside/headroom gates to isolate the core trend+breakout logic
    res = ss.screen_from_bars(_uptrend_bars(), account=20000, risk_pct=1.0,
                              min_upside_pct=0, min_headroom_pct=0)
    assert res["candidate"] is True
    # target is 2R above entry (levels are rounded to 3dp independently,
    # so allow a small rounding tolerance)
    assert abs((res["target"] - res["entry"]) - 2 * (res["entry"] - res["stop"])) < 0.01
    # risk respects the 1% budget
    assert res["risk"] <= 20000 * 0.01 + 1e-6


def test_downtrend_is_not_a_candidate():
    # steadily falling series -> price below its moving averages -> no trade
    bars = _trend_bars(n=260, start=12.0, step=-0.001)
    res = ss.screen_from_bars(bars)
    assert res["candidate"] is False
    assert res["reason"] == "not in uptrend"


def test_insufficient_history_rejected():
    res = ss.screen_from_bars(_uptrend_bars(n=30))
    assert res["candidate"] is False
    assert res["reason"] == "insufficient history"


def test_snapshot_near_52w_high_is_candidate():
    # h52 gives ~14% headroom; relaxing upside keeps the focus on positioning
    res = ss.screen_from_snapshot(close=10.0, prev_close=9.6, high=10.0, low=9.5,
                                  h52=11.4, l52=6.0, change_pct=4.0, account=20000,
                                  min_upside_pct=0)
    assert res["candidate"] is True
    assert res["pos52"] >= 55


def test_low_upside_is_rejected():
    # snapshot 2R target is ~10% (5% stop floor x2); a 12% gate rejects it
    res = ss.screen_from_snapshot(close=10.0, prev_close=9.9, high=10.0, low=9.8,
                                  h52=11.0, l52=6.0, change_pct=1.0,
                                  min_upside_pct=12.0, min_headroom_pct=0)
    assert res["candidate"] is False
    assert "upside" in res["reason"]


def test_at_52w_ceiling_is_rejected():
    # only ~2% room to the 52-week high -> below the 4% headroom gate
    res = ss.screen_from_snapshot(close=10.0, prev_close=9.6, high=10.0, low=9.5,
                                  h52=10.2, l52=6.0, change_pct=4.0,
                                  min_headroom_pct=4.0)
    assert res["candidate"] is False
    assert "ceiling" in res["reason"]


def test_max_price_filter_rejects_pricey_share():
    res = ss.screen_from_snapshot(close=50.0, prev_close=48.0, high=50.0, low=47.0,
                                  h52=55.0, l52=30.0, change_pct=3.0,
                                  max_price=20.0, min_upside_pct=0)
    assert res["candidate"] is False
    assert "price >" in res["reason"]


def test_snapshot_mid_range_rejected():
    res = ss.screen_from_snapshot(close=8.0, prev_close=8.0, high=8.1, low=7.9,
                                  h52=12.0, l52=6.0, change_pct=0.0)
    assert res["candidate"] is False


def test_position_cap_limits_shares():
    # tiny stop distance -> risk budget would buy a huge position; cap must bind
    res = ss.screen_from_snapshot(close=1.0, prev_close=0.99, high=1.0, low=0.999,
                                  h52=1.15, l52=0.6, change_pct=2.0,
                                  account=20000, risk_pct=1.0, max_pos_pct=20.0,
                                  min_upside_pct=0, min_headroom_pct=0)
    assert res["candidate"] is True
    assert res["cost"] <= 20000 * 0.20 + 1e-6
