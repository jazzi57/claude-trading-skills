"""Tests for the deterministic candlestick pattern detector."""

import csv

import pytest
from detect_candlestick_patterns import (
    Candle,
    aggregate_signal,
    detect_patterns,
    load_ohlcv,
    scan,
)


def C(o, h, low, c, date="d", vol=0.0):
    return Candle(date=date, open=o, high=h, low=low, close=c, volume=vol)


def _downtrend(n=5, start=120.0, step=-3.0):
    """A clean descending series of small bearish candles."""
    candles = []
    price = start
    for i in range(n):
        o = price
        cl = price + step
        candles.append(C(o, o + 0.5, cl - 0.5, cl, date=f"down{i}"))
        price = cl
    return candles


def _uptrend(n=5, start=80.0, step=3.0):
    candles = []
    price = start
    for i in range(n):
        o = price
        cl = price + step
        candles.append(C(o, cl + 0.5, o - 0.5, cl, date=f"up{i}"))
        price = cl
    return candles


# --------------------------------------------------------------------------- #
# Candle geometry
# --------------------------------------------------------------------------- #
def test_candle_geometry():
    c = C(10, 15, 8, 12)
    assert c.body == 2
    assert c.range == 7
    assert c.upper_shadow == 3  # 15 - max(10,12)
    assert c.lower_shadow == 2  # min(10,12) - 8
    assert c.is_bullish
    assert not c.is_bearish
    assert c.midpoint == 11


# --------------------------------------------------------------------------- #
# Single-candle patterns
# --------------------------------------------------------------------------- #
def test_doji_detected():
    candles = _uptrend(3) + [C(100, 105, 95, 100.2, date="doji")]
    hits = {h.name for h in detect_patterns(candles)}
    assert "doji" in hits


def test_hammer_after_downtrend_is_bullish():
    candles = _downtrend(5)
    # hammer: small body at top, long lower shadow
    candles.append(C(105.0, 105.5, 98.0, 105.2, date="hammer"))
    hits = [h for h in detect_patterns(candles) if h.name == "hammer"]
    assert hits, "hammer should be detected after a downtrend"
    assert hits[0].signal == "bullish"


def test_shooting_star_after_uptrend_is_bearish():
    candles = _uptrend(5)
    # shooting star: small body at bottom, long upper shadow
    candles.append(C(95.0, 102.0, 94.7, 95.2, date="star"))
    hits = [h for h in detect_patterns(candles) if h.name == "shooting_star"]
    assert hits, "shooting star should be detected after an uptrend"
    assert hits[0].signal == "bearish"


# --------------------------------------------------------------------------- #
# Double-candle patterns
# --------------------------------------------------------------------------- #
def test_bullish_engulfing():
    candles = _downtrend(4)
    candles.append(C(100.0, 100.2, 97.0, 97.5, date="prev"))  # small bearish
    candles.append(C(97.0, 103.0, 96.5, 102.0, date="eng"))  # big bullish engulfs
    hits = [h for h in detect_patterns(candles) if h.name == "bullish_engulfing"]
    assert hits
    assert hits[0].signal == "bullish"


def test_bearish_engulfing():
    candles = _uptrend(4)
    candles.append(C(100.0, 101.5, 99.8, 101.0, date="prev"))  # small bullish
    candles.append(C(102.0, 102.2, 98.0, 98.5, date="eng"))  # big bearish engulfs
    hits = [h for h in detect_patterns(candles) if h.name == "bearish_engulfing"]
    assert hits
    assert hits[0].signal == "bearish"


def test_bullish_harami():
    candles = _downtrend(4)
    candles.append(C(110.0, 110.5, 99.5, 100.0, date="big"))  # large bearish
    candles.append(C(102.0, 105.0, 101.5, 104.0, date="small"))  # small bullish inside
    hits = [h for h in detect_patterns(candles) if h.name == "bullish_harami"]
    assert hits


# --------------------------------------------------------------------------- #
# Triple-candle patterns
# --------------------------------------------------------------------------- #
def test_morning_star():
    candles = _downtrend(4)
    candles.append(C(110.0, 110.5, 100.0, 100.5, date="a"))  # big bearish
    candles.append(C(99.0, 100.0, 98.0, 99.2, date="b"))  # small body (star)
    candles.append(C(100.0, 112.0, 99.5, 111.0, date="c"))  # big bullish
    hits = [h for h in detect_patterns(candles) if h.name == "morning_star"]
    assert hits
    assert hits[0].signal == "bullish"


def test_three_white_soldiers():
    candles = _downtrend(3)
    candles.append(C(100, 105, 99, 104, date="s1"))
    candles.append(C(104, 109, 103, 108, date="s2"))
    candles.append(C(108, 113, 107, 112, date="s3"))
    hits = [h for h in detect_patterns(candles) if h.name == "three_white_soldiers"]
    assert hits


def test_three_black_crows():
    candles = _uptrend(3)
    candles.append(C(112, 113, 107, 108, date="c1"))
    candles.append(C(108, 109, 103, 104, date="c2"))
    candles.append(C(104, 105, 99, 100, date="c3"))
    hits = [h for h in detect_patterns(candles) if h.name == "three_black_crows"]
    assert hits


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def test_aggregate_bullish_signal():
    candles = _downtrend(4)
    candles.append(C(100.0, 100.2, 97.0, 97.5, date="prev"))
    candles.append(C(97.0, 103.0, 96.5, 102.0, date="eng"))  # bullish engulfing
    result = scan(candles)
    assert result.signal == "BUY"
    assert result.score > 0
    assert result.confidence in ("low", "medium", "high")


def test_aggregate_bearish_signal():
    candles = _uptrend(4)
    candles.append(C(100.0, 101.5, 99.8, 101.0, date="prev"))
    candles.append(C(102.0, 102.2, 98.0, 98.5, date="eng"))  # bearish engulfing
    result = scan(candles)
    assert result.signal == "SELL"
    assert result.score < 0


def test_aggregate_neutral_when_no_recent_patterns():
    # Plain rising candles with no reversal patterns in the last window
    candles = _uptrend(6)
    result = aggregate_signal(candles, [], lookback=3)
    assert result.signal == "NEUTRAL"
    assert result.confidence == "none"


def test_empty_candles_is_neutral():
    result = aggregate_signal([], [], lookback=3)
    assert result.signal == "NEUTRAL"


# --------------------------------------------------------------------------- #
# CSV loading
# --------------------------------------------------------------------------- #
def test_load_ohlcv_roundtrip(tmp_path):
    p = tmp_path / "data.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
        w.writerow(["2026-01-01", "100", "105", "99", "104", "1000"])
        w.writerow(["2026-01-02", "104", "108", "103", "107", "1200"])
    candles = load_ohlcv(str(p))
    assert len(candles) == 2
    assert candles[0].close == 104
    assert candles[1].volume == 1200


def test_load_ohlcv_missing_columns(tmp_path):
    p = tmp_path / "bad.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Open", "Close"])  # missing high/low
        w.writerow(["2026-01-01", "100", "104"])
    with pytest.raises(ValueError, match="missing required columns"):
        load_ohlcv(str(p))


def test_load_ohlcv_malformed_number(tmp_path):
    p = tmp_path / "bad2.csv"
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Date", "Open", "High", "Low", "Close"])
        w.writerow(["2026-01-01", "100", "x", "99", "104"])
    with pytest.raises(ValueError, match="Malformed numeric data"):
        load_ohlcv(str(p))


def test_load_ohlcv_empty_file(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("")
    with pytest.raises(ValueError):
        load_ohlcv(str(p))
