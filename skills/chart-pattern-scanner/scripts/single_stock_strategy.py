"""Single-stock mean-reversion trading mechanism (built for Air Arabia / AIRARABIA).

Rationale: the DFM backtest (references/dfm_backtest_findings.md) showed the
market *mean-reverts* against momentum extremes rather than trending on
candlestick signals. This mechanism encodes that as a transparent, long-only
rule set and backtests it on a single stock's own history:

- **Entry (long):** RSI(period) closes below `rsi_buy` (oversold) — buy the dip.
- **Exit:** RSI closes above `rsi_exit` (reverted), OR a stop (close <= entry*(1-stop_pct)),
  OR a time stop after `max_hold` bars.
- Long-only (retail shorting on DFM is constrained); close-to-close fills (no
  intraday data in the historical feed). The DFM −5% daily-limit means a close
  can't gap below −5% in a session, so an 8% stop realistically takes ≥2 sessions
  — surfaced via `daily_limit` in reporting.

Pure functions (`rsi`, `run_backtest`, `current_signal`) are unit-tested offline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect_candlestick_patterns import Candle  # noqa: E402


def rsi(closes: list, period: int = 14) -> list:
    """Wilder's RSI. Returns a list aligned to closes; None until warmed up."""
    out: list = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    avg_gain, avg_loss = gains / period, losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(ch, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-ch, 0.0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def run_backtest(
    candles: list,
    period: int = 14,
    rsi_buy: float = 35.0,
    rsi_exit: float = 55.0,
    stop_pct: float = 0.08,
    max_hold: int = 15,
) -> dict:
    """Backtest the mean-reversion rule on one stock. Long-only, close-to-close."""
    closes = [c.close for c in candles]
    r = rsi(closes, period)
    trades: list = []
    pos = None
    for i in range(len(candles)):
        if r[i] is None:
            continue
        price = closes[i]
        if pos is None:
            if r[i] < rsi_buy:
                pos = {"entry": price, "entry_i": i}
        else:
            held = i - pos["entry_i"]
            stop = price <= pos["entry"] * (1 - stop_pct)
            if r[i] > rsi_exit or stop or held >= max_hold:
                ret = price / pos["entry"] - 1
                reason = "stop" if stop else ("rsi_exit" if r[i] > rsi_exit else "time")
                trades.append(
                    {
                        "entry_date": candles[pos["entry_i"]].date,
                        "exit_date": candles[i].date,
                        "entry": round(pos["entry"], 4),
                        "exit": round(price, 4),
                        "return": round(ret, 4),
                        "held": held,
                        "reason": reason,
                    }
                )
                pos = None

    # metrics
    n = len(trades)
    wins = sum(1 for t in trades if t["return"] > 0)
    avg_ret = sum(t["return"] for t in trades) / n if n else 0.0
    equity = 1.0
    for t in trades:
        equity *= 1 + t["return"]
    total_ret = equity - 1
    # buy & hold over the usable window
    warm = next((i for i in range(len(r)) if r[i] is not None), len(closes) - 1)
    bh = closes[-1] / closes[warm] - 1 if closes[warm] else 0.0
    avg_hold = sum(t["held"] for t in trades) / n if n else 0.0
    return {
        "trades": trades,
        "n_trades": n,
        "win_rate": round(wins / n, 3) if n else None,
        "avg_return_per_trade": round(avg_ret, 4),
        "strategy_total_return": round(total_ret, 4),
        "buy_hold_return": round(bh, 4),
        "avg_hold_days": round(avg_hold, 1),
        "open_position": pos is not None,
    }


def sma(values: list, period: int) -> list:
    """Simple moving average aligned to values; None until warmed up."""
    out: list = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= period:
            run -= values[i - period]
        if i >= period - 1:
            out[i] = run / period
    return out


def run_backtest_trend(candles: list, sma_period: int = 20) -> dict:
    """Trend-following: long while close > SMA, flat while below. Long-only.

    Better suited to a trending name (e.g. Air Arabia) than mean-reversion.
    """
    closes = [c.close for c in candles]
    m = sma(closes, sma_period)
    trades: list = []
    pos = None
    for i in range(len(candles)):
        if m[i] is None:
            continue
        price = closes[i]
        if pos is None and price > m[i]:
            pos = {"entry": price, "entry_i": i}
        elif pos is not None and price < m[i]:
            ret = price / pos["entry"] - 1
            trades.append(
                {
                    "entry_date": candles[pos["entry_i"]].date,
                    "exit_date": candles[i].date,
                    "entry": round(pos["entry"], 4),
                    "exit": round(price, 4),
                    "return": round(ret, 4),
                    "held": i - pos["entry_i"],
                    "reason": "trend_break",
                }
            )
            pos = None
    if pos is not None:  # mark open position to last close
        ret = closes[-1] / pos["entry"] - 1
        trades.append(
            {
                "entry_date": candles[pos["entry_i"]].date,
                "exit_date": candles[-1].date,
                "entry": round(pos["entry"], 4),
                "exit": round(closes[-1], 4),
                "return": round(ret, 4),
                "held": len(candles) - 1 - pos["entry_i"],
                "reason": "open",
            }
        )
    n = len(trades)
    wins = sum(1 for t in trades if t["return"] > 0)
    equity = 1.0
    for t in trades:
        equity *= 1 + t["return"]
    warm = next((i for i in range(len(m)) if m[i] is not None), len(closes) - 1)
    bh = closes[-1] / closes[warm] - 1 if closes[warm] else 0.0
    return {
        "trades": trades,
        "n_trades": n,
        "win_rate": round(wins / n, 3) if n else None,
        "avg_return_per_trade": round(sum(t["return"] for t in trades) / n, 4) if n else 0.0,
        "strategy_total_return": round(equity - 1, 4),
        "buy_hold_return": round(bh, 4),
        "avg_hold_days": round(sum(t["held"] for t in trades) / n, 1) if n else 0.0,
        "open_position": pos is not None,
    }


def current_signal_trend(candles: list, sma_period: int = 20) -> dict:
    """Current trend state: long-bias if last close > SMA, else flat."""
    closes = [c.close for c in candles]
    m = sma(closes, sma_period)
    if m[-1] is None:
        return {"signal": "NONE", "note": "insufficient data"}
    above = closes[-1] > m[-1]
    return {
        "signal": "LONG-BIAS (above SMA)" if above else "FLAT/AVOID (below SMA)",
        "last": round(closes[-1], 4),
        "sma": round(m[-1], 4),
    }


def current_signal(
    candles: list, period: int = 14, rsi_buy: float = 35.0, rsi_exit: float = 55.0
) -> dict:
    """Current rule state on the latest bar."""
    closes = [c.close for c in candles]
    r = rsi(closes, period)
    last_rsi = r[-1] if r else None
    if last_rsi is None:
        return {"signal": "NONE", "rsi": None, "note": "insufficient data"}
    if last_rsi < rsi_buy:
        sig = "BUY (oversold)"
    elif last_rsi > rsi_exit:
        sig = "EXIT/AVOID (reverted/overbought)"
    else:
        sig = "HOLD/NEUTRAL"
    return {"signal": sig, "rsi": round(last_rsi, 1), "last": round(closes[-1], 4)}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_candles(series_json: str, symbol: str) -> list:
    raw = json.load(open(series_json, encoding="utf-8"))
    if symbol not in raw:
        raise KeyError(f"{symbol} not in {series_json} (have {len(raw)} symbols)")
    return [
        Candle(
            b["date"],
            b["open"],
            b["high"],
            b["low"],
            b["close"],
            b.get("volume", b.get("vol", 0)) or 0,
        )
        for b in raw[symbol]
    ]


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="Single-stock mean-reversion mechanism + backtest.")
    p.add_argument("--series-json", default="reports/dfm_history/_all_series.json")
    p.add_argument("--symbol", default="AIRARABIA")
    p.add_argument(
        "--mode",
        choices=["meanrev", "trend"],
        default="trend",
        help="trend = SMA trend-follow (fits trending names); meanrev = RSI dip-buy",
    )
    p.add_argument("--rsi-buy", type=float, default=35.0)
    p.add_argument("--rsi-exit", type=float, default=55.0)
    p.add_argument("--stop-pct", type=float, default=0.08)
    p.add_argument("--max-hold", type=int, default=15)
    p.add_argument("--sma", type=int, default=20)
    args = p.parse_args(argv)

    try:
        candles = _load_candles(args.series_json, args.symbol)
    except (OSError, KeyError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.mode == "trend":
        bt = run_backtest_trend(candles, sma_period=args.sma)
        sig = current_signal_trend(candles, sma_period=args.sma)
        label = f"trend-follow SMA{args.sma}"
        cur = f"{sig['signal']} (last {sig.get('last')}, SMA {sig.get('sma')})"
    else:
        bt = run_backtest(
            candles,
            rsi_buy=args.rsi_buy,
            rsi_exit=args.rsi_exit,
            stop_pct=args.stop_pct,
            max_hold=args.max_hold,
        )
        sig = current_signal(candles, rsi_buy=args.rsi_buy, rsi_exit=args.rsi_exit)
        label = "mean-reversion RSI"
        cur = f"{sig['signal']} (RSI {sig['rsi']}, last {sig.get('last')})"

    print(f"=== {args.symbol} — {label} ({len(candles)} bars) ===")
    print(
        f"Trades: {bt['n_trades']} | win-rate: {bt['win_rate']} | "
        f"avg/trade: {bt['avg_return_per_trade'] * 100:+.1f}% | avg hold: {bt['avg_hold_days']}d"
    )
    print(
        f"Strategy total: {bt['strategy_total_return'] * 100:+.1f}%  vs  buy&hold: {bt['buy_hold_return'] * 100:+.1f}%"
    )
    print(f"Current: {cur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
