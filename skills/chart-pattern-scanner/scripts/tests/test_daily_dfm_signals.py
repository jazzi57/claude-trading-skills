"""Offline tests for the daily DFM signal runner (pure logic)."""

from daily_dfm_signals import (
    pair_signals,
    recent_volume_reversals,
    scan_volume_reversals,
)
from detect_candlestick_patterns import Candle


def _hanging_man_on_last_bar(high_volume: bool):
    """Build an uptrend then a hanging-man bar (small body up top, long lower
    wick) as the final bar, with high or normal volume."""
    candles = []
    price = 100.0
    for i in range(25):
        price += 1.0
        candles.append(Candle(f"u{i:02d}", price - 0.5, price + 0.5, price - 0.7, price, 1000))
    # hanging man: opens high, long lower shadow, closes near the open at the top
    last_vol = 5000 if high_volume else 800
    candles.append(Candle("LAST", price + 0.9, price + 1.0, price - 1.5, price + 0.85, last_vol))
    return candles


def test_recent_volume_reversals_flags_high_volume_hit():
    candles = _hanging_man_on_last_bar(high_volume=True)
    hits = recent_volume_reversals(
        candles, patterns=("hanging_man", "shooting_star"),
        lookback=20, mult=1.5, within=1,
    )
    names = {h["pattern"] for h in hits}
    # a high-volume bearish reversal on the last bar should be flagged
    assert "hanging_man" in names or "shooting_star" in names
    for h in hits:
        assert h["volume_bucket"] == "high"
        assert h["bars_ago"] == 0


def test_recent_volume_reversals_skips_normal_volume():
    candles = _hanging_man_on_last_bar(high_volume=False)
    hits = recent_volume_reversals(
        candles, patterns=("hanging_man", "shooting_star"),
        lookback=20, mult=1.5, within=1,
    )
    assert hits == []  # only high-volume reversals qualify


def test_recent_volume_reversals_respects_within_window():
    candles = _hanging_man_on_last_bar(high_volume=True)
    # add two more ordinary bars so the reversal is 2 bars back
    p = candles[-1].close
    candles.append(Candle("x1", p, p + 0.3, p - 0.3, p + 0.1, 1000))
    candles.append(Candle("x2", p, p + 0.3, p - 0.3, p + 0.1, 1000))
    assert recent_volume_reversals(candles, ("hanging_man", "shooting_star"), 20, 1.5, within=1) == []
    later = recent_volume_reversals(candles, ("hanging_man", "shooting_star"), 20, 1.5, within=5)
    assert any(h["bars_ago"] == 2 for h in later)


def test_scan_volume_reversals_across_symbols():
    series = {
        "HIT": _hanging_man_on_last_bar(high_volume=True),
        "MISS": _hanging_man_on_last_bar(high_volume=False),
    }
    rows = scan_volume_reversals(series, ("hanging_man", "shooting_star"), 20, 1.5, within=1)
    syms = {r["symbol"] for r in rows}
    assert "HIT" in syms
    assert "MISS" not in syms


def test_pair_signals_reports_each_pair():
    n = 30
    b = [{"date": f"d{i:02d}", "close": 10.0} for i in range(n)]
    a = [{"date": f"d{i:02d}", "close": 10.0} for i in range(n - 1)]
    a.append({"date": f"d{n - 1:02d}", "close": 13.0})  # A jumps -> ratio stretched
    series = {"EMAAR": a, "EMAARDEV": b}
    out = pair_signals(series, [("EMAAR", "EMAARDEV")], lookback=10, entry_z=1.0)
    assert len(out) == 1
    assert out[0]["a"] == "EMAAR" and out[0]["b"] == "EMAARDEV"
    assert out[0]["z"] is not None


def test_pair_signals_skips_missing_symbol():
    out = pair_signals({"EMAAR": []}, [("EMAAR", "NOPE")], lookback=10, entry_z=1.0)
    assert out == []
