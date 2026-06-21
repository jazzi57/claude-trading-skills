"""Offline tests for the DFM market-scan pipeline (pure logic)."""

from scan_dfm_market import render_report_md, scan_series, sort_rows


def _downtrend_then_engulf():
    """Synthetic series ending in a bullish engulfing -> BUY."""
    bars = []
    price = 120.0
    for i in range(25):
        o = price
        c = price - 2
        bars.append(
            {"date": f"2026-05-{i + 1:02d}", "open": o, "high": o + 0.5, "low": c - 0.5, "close": c}
        )
        price = c
    # small bearish then large bullish engulfing
    bars.append({"date": "2026-06-01", "open": 60.0, "high": 60.2, "low": 57.0, "close": 57.5})
    bars.append({"date": "2026-06-02", "open": 57.0, "high": 63.0, "low": 56.5, "close": 62.0})
    return bars


def _flat_series():
    bars = []
    for i in range(25):
        bars.append(
            {"date": f"2026-05-{i + 1:02d}", "open": 10, "high": 10.2, "low": 9.8, "close": 10}
        )
    return bars


def test_scan_series_detects_buy():
    rows = scan_series({"TEST": _downtrend_then_engulf()}, min_bars=20)
    assert len(rows) == 1
    assert rows[0]["signal"] == "BUY"
    assert rows[0]["score"] > 0
    assert rows[0]["bars"] == 27


def test_scan_series_marks_nodata_when_too_few_bars():
    rows = scan_series(
        {"THIN": [{"date": "2026-06-01", "open": 1, "high": 1, "low": 1, "close": 1}]}, min_bars=20
    )
    assert rows[0]["signal"] == "NODATA"
    assert rows[0]["last"] == 1


def test_scan_series_handles_vol_key_alias():
    bars = _downtrend_then_engulf()
    bars[-1]["vol"] = 999  # ensure 'vol' alias doesn't crash
    rows = scan_series({"TEST": bars}, min_bars=20)
    assert rows[0]["signal"] == "BUY"


def test_sort_rows_orders_buy_then_sell_then_neutral():
    rows = [
        {"symbol": "N", "signal": "NEUTRAL", "score": 0.0},
        {"symbol": "S1", "signal": "SELL", "score": -0.6},
        {"symbol": "S2", "signal": "SELL", "score": -1.2},
        {"symbol": "B", "signal": "BUY", "score": 0.7},
    ]
    ordered = [r["symbol"] for r in sort_rows(rows)]
    assert ordered == ["B", "S2", "S1", "N"]  # BUY, then SELL by |score|, then neutral


def test_render_report_md_structure():
    rows = [
        {
            "symbol": "B",
            "last": 1.2,
            "signal": "BUY",
            "score": 0.7,
            "confidence": "medium",
            "latest_pattern": "hammer @x",
            "bars": 30,
            "result": None,
        },
        {
            "symbol": "S",
            "last": 3.0,
            "signal": "SELL",
            "score": -1.1,
            "confidence": "high",
            "latest_pattern": "bearish_engulfing @x",
            "bars": 30,
            "result": None,
        },
        {
            "symbol": "N",
            "last": 5.0,
            "signal": "NEUTRAL",
            "score": 0.0,
            "confidence": "none",
            "latest_pattern": "-",
            "bars": 30,
            "result": None,
        },
        {
            "symbol": "X",
            "last": 9.0,
            "signal": "NODATA",
            "score": 0.0,
            "confidence": "none",
            "latest_pattern": "only 3 bars",
            "bars": 3,
            "result": None,
        },
    ]
    md = render_report_md(rows, "2026-06-20", "Official DFM API")
    assert "# DFM Market-Wide Candlestick Scan" in md
    assert "BUY 1 · SELL 1 · NEUTRAL/none 2" in md  # NODATA counts under others
    assert "Universe:** 3 scanned (4 symbols total)" in md
    assert "**BUY**" in md and "**SELL**" in md
    assert "N(5.0)" in md  # neutral listing
    assert "not financial advice" in md
