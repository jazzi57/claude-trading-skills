# Backtrader Pullback-Window Strategy — XAUUSD (vendored)

Ported, runnable copy of the **Sunrise Ogle** gold (XAU/USD) pullback strategy
for [Backtrader](https://www.backtrader.com/). It implements a 4-phase
"volatility expansion channel" entry: scan for an EMA crossover → wait for a
1–3 candle counter-trend pullback → open a breakout window → enter only on a
confirmed breakout, with ATR-based stop-loss / take-profit OCA bracket orders.

> ⚠️ **Educational / research use only. Not investment advice.** Past
> performance does not guarantee future results. Validate all logic and data
> quality before any live or simulated use.

## Provenance

- **Upstream:** https://github.com/ilahuerta-IA/backtrader-pullback-window-xauusd
- **License:** MIT (see `LICENSE` in this directory)
- **Core strategy logic** in `sunrise_ogle_xauusd.py` is kept faithful to
  upstream. The only changes made during the port are confined to the
  `if __name__ == '__main__'` run harness (a CLI replacing edit-the-constants
  configuration) and gating two stray `print()` debug lines behind the existing
  `verbose_debug` flag. The directory is excluded from the repo's `ruff` /
  `codespell` pre-commit hooks so it stays byte-faithful to the source.

The upstream README reports a 5-year backtest (Jul 2020–Jul 2025) of
Sharpe 0.89, PF 1.64, win rate 55.4%, max DD 5.8%, +44.75% return over 175
trades. Those numbers depend on the upstream 5-year dataset, which is **not**
vendored here (it is ~20 MB; this repo caps committed files at 500 KB).

## What's here

| File | Purpose |
|------|---------|
| `sunrise_ogle_xauusd.py` | The strategy + Backtrader run harness (CLI). |
| `generate_sample_data.py` | Creates a small **synthetic** 5-min OHLCV CSV so the backtest runs out of the box. |
| `requirements.txt` | Pinned dependencies from upstream (`backtrader==1.9.76.123`, NumPy, Matplotlib…). |
| `data/` | Drop your real CSV here (git-ignored). |

## Quick start

```bash
# 1. Install dependencies (a virtualenv is recommended)
pip install -r requirements.txt

# 2. Generate a synthetic dataset (writes data/XAUUSD_5m_sample.csv)
python generate_sample_data.py

# 3. Run the backtest headless on the sample data
python sunrise_ogle_xauusd.py --data data/XAUUSD_5m_sample.csv --quiet
```

The synthetic feed is a deterministic random walk — it only proves the
pipeline runs. For meaningful results, supply a real XAUUSD 5-minute feed.

## Using real data

Provide any CSV with this exact header and column order:

```
Date,Time,Open,High,Low,Close,Volume
20200821,00:00:00,1952.57,1955.77,1951.61,1955.48,380670
```

`Date` is `%Y%m%d`, `Time` is `%H:%M:%S`, bars are 5-minute. Point the runner at
it:

```bash
python sunrise_ogle_xauusd.py \
  --data /path/to/XAUUSD_5m.csv \
  --fromdate 2020-07-10 --todate 2025-07-25 \
  --cash 100000 --direction long
```

## CLI options

| Flag | Default | Description |
|------|---------|-------------|
| `--data PATH` | `data/<DATA_FILENAME>` | OHLCV CSV to backtest. |
| `--fromdate YYYY-MM-DD` | file constant | Backtest start date. |
| `--todate YYYY-MM-DD` | file constant | Backtest end date. |
| `--cash FLOAT` | `100000` | Starting cash (USD). |
| `--leverage FLOAT` | `30.0` | Broker leverage. |
| `--direction {long,short,both}` | file config | Override trading direction. |
| `--limit-bars N` | `0` | Stop after N bars (0 = no limit). |
| `--quick-test` | off | Reduce to the last 10 days for a fast smoke test. |
| `--plot` | off | Show the Matplotlib chart (needs a display backend). |
| `--quiet` | off | Suppress verbose per-bar debug output. |

Strategy parameters (EMA lengths, ATR multipliers, pullback depth, window
periods, ATR volatility filters, …) remain as module-level constants and a
`params` dict at the top of `sunrise_ogle_xauusd.py`; edit there to tune the
strategy, exactly as upstream.

## Runtime outputs

With trade reporting enabled (default), per-run trade logs are written to a
`temp_reports/` directory relative to your working directory. Both `data/*.csv`
and `temp_reports/` are git-ignored.
