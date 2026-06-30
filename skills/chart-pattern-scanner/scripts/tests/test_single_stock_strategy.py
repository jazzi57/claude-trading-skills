"""Offline tests for the single-stock mean-reversion mechanism."""

from detect_candlestick_patterns import Candle
from single_stock_strategy import (
    current_signal,
    current_signal_trend,
    rsi,
    run_backtest,
    run_backtest_trend,
    sma,
)


def _candles(closes):
    return [Candle(f"d{i}", c, c + 0.5, c - 0.5, c, 1000) for i, c in enumerate(closes)]


def test_rsi_warmup_and_bounds():
    closes = list(range(1, 30))  # strictly rising
    r = rsi(closes, 14)
    assert all(v is None for v in r[:14])
    assert r[14] is not None
    assert r[-1] > 90  # rising series -> high RSI


def test_rsi_falling_series_low():
    closes = list(range(40, 10, -1))  # strictly falling
    r = rsi(closes, 14)
    assert r[-1] < 10


def test_rsi_short_series_all_none():
    assert rsi([1, 2, 3], 14) == [None, None, None]


def test_backtest_takes_meanreversion_trade():
    # fall (drives RSI down) then recover (drives RSI up) -> one winning long
    closes = [100 - i for i in range(20)] + [80 + 2 * i for i in range(20)]
    bt = run_backtest(_candles(closes), rsi_buy=35, rsi_exit=55, stop_pct=0.5, max_hold=50)
    assert bt["n_trades"] >= 1
    assert bt["win_rate"] >= 0.5
    assert bt["strategy_total_return"] > 0


def test_backtest_stop_triggers():
    # enter oversold then keep falling -> stop closes the trade at a loss
    closes = [100 - i for i in range(20)] + [80 - i for i in range(10)]
    bt = run_backtest(_candles(closes), rsi_buy=40, rsi_exit=60, stop_pct=0.03, max_hold=50)
    assert any(t["reason"] == "stop" for t in bt["trades"])


def test_backtest_reports_buyhold():
    closes = [100 - i for i in range(20)] + [80 + 2 * i for i in range(20)]
    bt = run_backtest(_candles(closes))
    assert "buy_hold_return" in bt and isinstance(bt["buy_hold_return"], float)


def test_current_signal_oversold():
    closes = list(range(60, 20, -1))  # falling -> low RSI -> BUY
    sig = current_signal(_candles(closes), rsi_buy=35)
    assert sig["signal"].startswith("BUY")


def test_current_signal_insufficient():
    sig = current_signal(_candles([1, 2, 3]))
    assert sig["signal"] == "NONE"


# --- trend mode ---
def test_sma_warmup_and_value():
    m = sma([10, 20, 30, 40], 2)
    assert m[0] is None
    assert m[1] == 15.0
    assert m[3] == 35.0


def test_trend_backtest_captures_uptrend():
    closes = list(range(50, 110))  # steady uptrend
    bt = run_backtest_trend(_candles(closes), sma_period=10)
    assert bt["n_trades"] >= 1
    assert bt["strategy_total_return"] > 0


def test_trend_exits_on_breakdown():
    closes = list(range(50, 90)) + list(range(90, 60, -1))  # up then down
    bt = run_backtest_trend(_candles(closes), sma_period=10)
    # a trend break should close the long (no longer 'open')
    assert any(t["reason"] == "trend_break" for t in bt["trades"])


def test_current_signal_trend_long_bias():
    sig = current_signal_trend(_candles(list(range(50, 90))), sma_period=10)
    assert sig["signal"].startswith("LONG-BIAS")
