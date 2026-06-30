"""Offline tests for the pairs / spread strategy (pure logic)."""

import math

from pairs_strategy import (
    align_closes,
    current_pair_signal,
    log_ratio,
    rolling_z,
    run_pairs_backtest,
    scan_pairs,
)


def test_log_ratio():
    lr = log_ratio([10.0, 20.0], [10.0, 10.0])
    assert round(lr[0], 6) == 0.0
    assert round(lr[1], 6) == round(math.log(2.0), 6)


def test_rolling_z_warmup_none_then_value():
    series = [1.0, 2.0, 3.0, 4.0, 5.0]
    z = rolling_z(series, lookback=3)
    assert z[0] is None and z[1] is None  # not warmed up
    assert z[2] is not None
    # last point is the top of a rising window -> positive z
    assert z[4] > 0


def test_rolling_z_zero_variance_is_none():
    z = rolling_z([5.0, 5.0, 5.0, 5.0], lookback=3)
    assert z[3] is None  # std == 0


def test_align_closes_common_dates_only():
    a = [
        {"date": "2026-01-01", "close": 10.0},
        {"date": "2026-01-02", "close": 11.0},
        {"date": "2026-01-03", "close": 12.0},
    ]
    b = [
        {"date": "2026-01-02", "close": 5.0},
        {"date": "2026-01-03", "close": 6.0},
        {"date": "2026-01-04", "close": 7.0},
    ]
    dates, ac, bc = align_closes(a, b)
    assert dates == ["2026-01-02", "2026-01-03"]
    assert ac == [11.0, 12.0]
    assert bc == [5.0, 6.0]


def test_run_pairs_backtest_mean_reverting_pair_profits():
    # B is flat; A oscillates around B so the log-ratio mean-reverts.
    # A high -> short-spread should profit when A falls back.
    n = 60
    b = [10.0] * n
    a = [10.0 + (2.0 if i % 10 < 5 else -2.0) for i in range(n)]
    dates = [f"d{i:03d}" for i in range(n)]
    res = run_pairs_backtest(dates, a, b, lookback=10, entry_z=1.0, exit_z=0.2, stop_z=4.0)
    assert res["n_trades"] >= 1
    assert res["total_pnl"] is not None
    # market-neutral mean-reversion on a clean oscillator should not lose overall
    assert res["total_pnl"] > 0


def test_run_pairs_backtest_no_signal_when_flat_ratio():
    n = 40
    a = [10.0] * n
    b = [5.0] * n
    dates = [f"d{i:03d}" for i in range(n)]
    res = run_pairs_backtest(dates, a, b, lookback=10, entry_z=1.0, exit_z=0.2, stop_z=4.0)
    assert res["n_trades"] == 0


def _osc_series(n, dates, amp, phase=0):
    return [
        {"date": dates[i], "close": 10.0 + (amp if (i + phase) % 10 < 5 else -amp)}
        for i in range(n)
    ]


def test_scan_pairs_ranks_correlated_mean_reverting_pair_top():
    n = 80
    dates = [f"d{i:03d}" for i in range(n)]
    # A and B co-move (both oscillate in phase) -> high correlation; their ratio
    # still wiggles enough to trade. C is a flat line -> no signal with A.
    a = _osc_series(n, dates, amp=2.0)
    b = _osc_series(n, dates, amp=1.0)  # same phase, smaller amplitude
    c = [{"date": dates[i], "close": 50.0} for i in range(n)]
    res = scan_pairs(
        {"A": a, "B": b, "C": c},
        min_corr=0.3, min_overlap=40, lookback=10,
        entry_z=1.0, exit_z=0.2, stop_z=5.0, top=5, min_trades=1,
    )
    assert res, "expected at least one tradable pair"
    assert {res[0]["a"], res[0]["b"]} == {"A", "B"}
    assert res[0]["corr"] is not None
    assert res[0]["n_trades"] >= 1


def test_scan_pairs_filters_low_correlation():
    n = 80
    dates = [f"d{i:03d}" for i in range(n)]
    a = _osc_series(n, dates, amp=2.0, phase=0)
    b = _osc_series(n, dates, amp=2.0, phase=5)  # anti-phase -> negative corr
    res = scan_pairs(
        {"A": a, "B": b}, min_corr=0.8, min_overlap=40, lookback=10,
        entry_z=1.0, exit_z=0.2, stop_z=5.0, top=5, min_trades=1,
    )
    assert res == []  # correlation below threshold -> excluded


def test_scan_pairs_respects_min_overlap():
    n = 30
    dates = [f"d{i:03d}" for i in range(n)]
    a = _osc_series(n, dates, amp=2.0)
    b = _osc_series(n, dates, amp=1.0)
    res = scan_pairs(
        {"A": a, "B": b}, min_corr=0.0, min_overlap=100, lookback=10,
        entry_z=1.0, exit_z=0.2, stop_z=5.0, top=5, min_trades=1,
    )
    assert res == []  # not enough overlapping history


def test_current_pair_signal_reports_zscore():
    n = 30
    b = [10.0] * n
    a = [10.0] * (n - 1) + [13.0]  # last bar: A jumps -> ratio spikes high
    sig = current_pair_signal(a, b, lookback=10, entry_z=1.0)
    assert sig["z"] is not None
    assert "SHORT_SPREAD" in sig["signal"]  # A rich vs B -> short A / long B
