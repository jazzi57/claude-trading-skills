"""Offline tests for the correlation study (pure logic)."""

from correlation_study import (
    lag1_autocorr,
    lead_lag,
    market_factor,
    pct_returns,
    pearson,
    returns_by_date,
    top_pairs,
)


def test_pct_returns():
    assert pct_returns([100, 110, 99]) == [0.1, -0.1]


def test_pearson_perfect_positive():
    assert round(pearson([1, 2, 3, 4], [2, 4, 6, 8]), 6) == 1.0


def test_pearson_perfect_negative():
    assert round(pearson([1, 2, 3, 4], [8, 6, 4, 2]), 6) == -1.0


def test_pearson_zero_variance_or_short():
    assert pearson([1, 1, 1, 1], [1, 2, 3, 4]) is None
    assert pearson([1, 2], [1, 2]) is None


def test_lag1_autocorr_mean_reversion_negative():
    # strictly alternating sign returns -> strong negative lag-1 autocorr
    r = [0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.1, -0.1]
    assert lag1_autocorr(r) < -0.5


def test_lag1_autocorr_momentum_positive():
    r = [0.01, 0.02, 0.03, 0.02, 0.01, 0.02, 0.03, 0.04]  # persistent positive
    assert lag1_autocorr(r) is not None


def test_lead_lag_detects_one_day_lead():
    driver = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    target = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]  # target[t] == driver[t-1]
    assert round(lead_lag(driver, target, 1), 6) == 1.0


def test_returns_by_date():
    bars = [
        {"date": "2026-01-01", "close": 100},
        {"date": "2026-01-02", "close": 110},
        {"date": "2026-01-03", "close": 99},
    ]
    rd = returns_by_date(bars)
    assert round(rd["2026-01-02"], 4) == 0.1
    assert round(rd["2026-01-03"], 4) == -0.1


def test_market_factor_averages():
    ret_maps = {
        "A": {"d1": 0.10, "d2": -0.04},
        "B": {"d1": 0.20, "d2": 0.00},
    }
    mf = market_factor(ret_maps)
    assert round(mf["d1"], 4) == 0.15
    assert round(mf["d2"], 4) == -0.02


def test_top_pairs_finds_correlated():
    # A and B move together; C is opposite
    a = {f"d{i}": (0.01 if i % 2 else -0.01) for i in range(200)}
    b = {f"d{i}": (0.012 if i % 2 else -0.012) for i in range(200)}
    c = {f"d{i}": (-0.01 if i % 2 else 0.01) for i in range(200)}
    pairs = top_pairs({"A": a, "B": b, "C": c}, min_overlap=100, top=1)
    assert pairs[0][1:3] == ("A", "B")
    assert pairs[0][0] > 0.9
