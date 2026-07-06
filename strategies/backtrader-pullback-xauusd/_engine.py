"""Shared Backtrader harness for the ported strategy.

Used by report_state.py (current-state reporter) and retune_atr.py (parameter
calibration) so both drive the strategy the same way the main runner does,
without duplicating cerebro wiring. Not a CLI itself.
"""
from __future__ import annotations

import contextlib
import io
import statistics
from datetime import datetime, timezone
from pathlib import Path

import backtrader as bt

import sunrise_ogle_xauusd as strat_mod
from sunrise_ogle_xauusd import SunriseOgle

FEED_KW = dict(dtformat="%Y%m%d", tmformat="%H:%M:%S",
               datetime=0, time=1, open=2, high=3, low=4, close=5, volume=6,
               timeframe=bt.TimeFrame.Minutes, compression=5)


def build_feed(data_file: Path, fromdate: datetime | None = None,
               todate: datetime | None = None) -> bt.feeds.GenericCSVData:
    kw = dict(FEED_KW, dataname=str(data_file))
    if fromdate:
        kw["fromdate"] = fromdate
    if todate:
        kw["todate"] = todate
    return bt.feeds.GenericCSVData(**kw)


def run_backtest(data_file: Path, strat_kwargs: dict | None = None,
                 fromdate: datetime | None = None, todate: datetime | None = None,
                 cash: float = 100_000.0, leverage: float = 30.0):
    """Run one backtest; return (strategy_instance, metrics_dict).

    Trade-report file writing and the strategy's own stdout are suppressed so
    this is safe to call in a loop (parameter sweeps).
    """
    # Disable the strategy's per-run trade-report files (module-level flags).
    strat_mod.EXPORT_TRADE_REPORTS = False
    strat_mod.TRADE_REPORT_ENABLED = False

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.adddata(build_feed(data_file, fromdate, todate))
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(leverage=leverage)
    kw = dict(plot_result=False, use_forex_position_calc=True,
              forex_instrument="XAUUSD", verbose_debug=False)
    if strat_kwargs:
        kw.update(strat_kwargs)
    cerebro.addstrategy(SunriseOgle, **kw)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    with contextlib.redirect_stdout(io.StringIO()):
        strat = cerebro.run()[0]

    metrics = _summarize(strat, cerebro.broker.getvalue(), cash)
    return strat, metrics


def _summarize(strat, final_value: float, cash: float) -> dict:
    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.dd.get_analysis()
    total = ta.get("total", {}).get("total", 0) or 0
    won = ta.get("won", {}).get("total", 0) or 0
    lost = ta.get("lost", {}).get("total", 0) or 0
    gross_profit = (ta.get("won", {}).get("pnl", {}) or {}).get("total", 0.0) or 0.0
    gross_loss = abs((ta.get("lost", {}).get("pnl", {}) or {}).get("total", 0.0) or 0.0)
    avg_win = (ta.get("won", {}).get("pnl", {}) or {}).get("average", 0.0) or 0.0
    avg_loss = (ta.get("lost", {}).get("pnl", {}) or {}).get("average", 0.0) or 0.0
    win_rate = (won / total * 100.0) if total else 0.0
    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = float("inf")
    else:
        pf = 0.0
    expectancy = ((win_rate / 100.0) * avg_win) - ((1 - win_rate / 100.0) * abs(avg_loss))
    max_dd = (dd.get("max", {}) or {}).get("drawdown", 0.0) or 0.0
    return dict(
        total_trades=total, won=won, lost=lost, win_rate=win_rate,
        profit_factor=pf, expectancy=expectancy, net_pnl=final_value - cash,
        return_pct=(final_value / cash - 1) * 100.0, final_value=final_value,
        max_drawdown_pct=max_dd,
    )


def atr_series(data_file: Path, period: int = 10) -> list[float]:
    """Compute a simple ATR(period) directly from the CSV (for threshold calibration)."""
    import csv
    rows = list(csv.reader(open(data_file)))[1:]
    highs = [float(r[3]) for r in rows]
    lows = [float(r[4]) for r in rows]
    closes = [float(r[5]) for r in rows]
    trs = []
    for i in range(1, len(rows)):
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))
    return [statistics.mean(trs[i - period:i]) for i in range(period, len(trs))]


def csv_time_bounds(data_file: Path) -> tuple[datetime, datetime]:
    """First and last bar timestamps (UTC) in a strategy-format CSV."""
    import csv
    rows = list(csv.reader(open(data_file)))[1:]

    def _dt(r):
        return datetime.strptime(f"{r[0]} {r[1]}", "%Y%m%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return _dt(rows[0]), _dt(rows[-1])
