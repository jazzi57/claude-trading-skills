"""Offline tests for the candlestick pattern backtester (pure logic)."""

from backtest_patterns import (
    aggregate_stats,
    avg_prior_volume,
    forward_outcomes,
    summarize_pattern,
    summarize_pattern_volume,
    volume_bucket,
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


# --- volume confirmation ---------------------------------------------------- #


def test_avg_prior_volume_window():
    candles = [Candle(f"d{i}", 1, 1, 1, 1, vol) for i, vol in enumerate([10, 20, 30, 40, 50])]
    # average of the 3 bars strictly before idx 4 -> (20+30+40)/3 = 30
    assert avg_prior_volume(candles, 4, lookback=3) == 30.0


def test_avg_prior_volume_insufficient_history():
    candles = [Candle(f"d{i}", 1, 1, 1, 1, 10) for i in range(3)]
    assert avg_prior_volume(candles, 2, lookback=5) is None
    assert avg_prior_volume(candles, 0, lookback=3) is None


def test_volume_bucket_high_vs_normal():
    vols = [100] * 20 + [250]  # last bar is 2.5x the prior average
    candles = [Candle(f"d{i}", 1, 1, 1, 1, v) for i, v in enumerate(vols)]
    assert volume_bucket(candles, 20, lookback=20, mult=1.5) == "high"
    # a bar equal to the average is "normal"
    candles2 = [Candle(f"d{i}", 1, 1, 1, 1, 100) for i in range(21)]
    assert volume_bucket(candles2, 20, lookback=20, mult=1.5) == "normal"


def test_volume_bucket_none_when_no_history():
    candles = [Candle(f"d{i}", 1, 1, 1, 1, 100) for i in range(3)]
    assert volume_bucket(candles, 2, lookback=20, mult=1.5) is None


def test_summarize_pattern_volume_splits_buckets():
    candles = _series_up_after(5)
    res = summarize_pattern_volume(
        {"TEST": candles}, pattern_name="hammer", direction="bullish",
        horizons=(5,), lookback=3, mult=1.5,
    )
    assert set(res) == {"high", "normal", "all"}
    for bucket in res.values():
        assert 5 in bucket
        assert "n" in bucket[5]
