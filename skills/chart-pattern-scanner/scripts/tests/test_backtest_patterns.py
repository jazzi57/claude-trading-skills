"""Offline tests for the candlestick pattern backtester (pure logic)."""

from backtest_patterns import (
    aggregate_stats,
    forward_outcomes,
    summarize_pattern,
)
from detect_candlestick_patterns import Candle


def _series_up_after(n_pre=10):
    """Build candles that rise steadily after index n_pre (for forward-return tests)."""
    candles = []
    price = 100.0
    for i in range(n_pre):
        candles.append(Candle(f"d{i}", price, price + 1, price - 1, price, 1000))
    # from n_pre onward, rise 2/bar
    for i in range(10):
        price += 2
        candles.append(Candle(f"u{i}", price - 1, price + 1, price - 2, price, 1000))
    return candles


def test_forward_outcomes_direction_and_return():
    candles = _series_up_after(5)
    # event at index 5 (close=100), horizon 5 -> price has risen
    out = forward_outcomes(candles, idx=5, horizon=5)
    assert out["fwd_return"] > 0
    assert out["up"] is True


def test_forward_outcomes_insufficient_horizon_returns_none():
    candles = _series_up_after(5)
    assert forward_outcomes(candles, idx=len(candles) - 1, horizon=5) is None


def test_aggregate_stats_hit_rate():
    # 3 bullish outcomes: 2 up, 1 down -> hit rate 2/3
    outs = [
        {"fwd_return": 0.05, "up": True},
        {"fwd_return": 0.02, "up": True},
        {"fwd_return": -0.03, "up": False},
    ]
    st = aggregate_stats(outs, direction="bullish")
    assert st["n"] == 3
    assert round(st["hit_rate"], 2) == 0.67
    assert round(st["avg_return"], 4) == round((0.05 + 0.02 - 0.03) / 3, 4)


def test_aggregate_stats_bearish_hit_is_down():
    outs = [
        {"fwd_return": -0.04, "up": False},  # hit for bearish
        {"fwd_return": 0.01, "up": True},  # miss
    ]
    st = aggregate_stats(outs, direction="bearish")
    assert st["n"] == 2
    assert round(st["hit_rate"], 2) == 0.50


def test_aggregate_stats_empty():
    st = aggregate_stats([], direction="bullish")
    assert st["n"] == 0
    assert st["hit_rate"] is None


def test_summarize_pattern_runs_over_series():
    # A long downtrend then bullish engulfing repeated won't be needed;
    # just ensure summarize_pattern returns a dict keyed by horizon.
    candles = _series_up_after(5)
    res = summarize_pattern(
        {"TEST": candles}, pattern_name="hammer", direction="bullish", horizons=(5,)
    )
    assert 5 in res
    assert "n" in res[5]
