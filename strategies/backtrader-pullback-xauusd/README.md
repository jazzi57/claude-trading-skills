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
| `fetch_data.py` | Downloads **real** gold 5-min OHLCV (Yahoo, keyless; or FMP). |
| `report_state.py` | Reports the model's **current** state + levels on the latest bar. |
| `retune_atr.py` | Recalibrates ATR/angle params to the current regime (in/out-of-sample). |
| `_engine.py` | Shared Backtrader harness used by the two scripts above. |
| `generate_sample_data.py` | Creates a small **synthetic** 5-min OHLCV CSV so the backtest runs with no network. |
| `requirements.txt` | Pinned dependencies from upstream (`backtrader==1.9.76.123`, NumPy, Matplotlib…). |
| `data/` | Fetched / generated CSVs land here (git-ignored). |

## Quick start (real data)

```bash
# 1. Install dependencies (a virtualenv is recommended)
pip install -r requirements.txt

# 2. One command: fetch fresh real gold bars AND backtest them
python sunrise_ogle_xauusd.py --fetch --quiet
```

`--fetch` downloads fresh real OHLCV inline (Yahoo `GC=F`, no API key) right
before the run, so you never have to manage a CSV by hand. Equivalent two-step:

```bash
python fetch_data.py                                  # writes data/GCF_5m.csv
python sunrise_ogle_xauusd.py --data data/GCF_5m.csv --quiet
```

## Fetching data

`fetch_data.py` writes a CSV in the strategy's exact format. It uses `requests`
(not yfinance's curl_cffi backend), so it works behind proxies that re-terminate
TLS.

```bash
python fetch_data.py                          # GC=F (COMEX gold futures), last 60d
python fetch_data.py --range 30d              # shorter window
python fetch_data.py --symbol XAUUSD=X        # Yahoo spot gold (volume is 0)
python fetch_data.py --source fmp --symbol XAUUSD   # FMP (needs FMP_API_KEY)
```

| Source | Key | Symbol default | History | Notes |
|--------|-----|----------------|---------|-------|
| `yahoo` (default) | none | `GC=F` | ~60 days for 5-min bars | Yahoo Finance public chart endpoint. |
| `fmp` | `FMP_API_KEY` | `XAUUSD` | longer on paid tiers | Financial Modeling Prep intraday endpoint. |

> ⚠️ **Parameter calibration.** The strategy's bundled ATR volatility filters
> use absolute thresholds tuned for the upstream 2020–2025 dataset (e.g.
> `LONG_ATR_MAX_THRESHOLD = 2.00`, and forex-scale `SHORT_ATR_*` values like
> `0.0004`). Today's gold trades near $4,800 with a 5-min ATR(10) around 5, so
> those filters reject **every** entry and you'll see 0 trades. Either retune
> the `*_ATR_*` constants at the top of `sunrise_ogle_xauusd.py` to the current
> price regime, or pass `--no-atr-filter` to bypass them and sanity-check the
> entry logic on freshly fetched data.

## Calibrating to the current regime + reading the live state

Two helpers make the model usable on current data instead of just backtestable.

**1. Retune parameters to today's regime (`retune_atr.py`).** Derives the ATR
filter band from the data's own ATR distribution, disables the finicky ATR
increment/decrement sub-filters, drops the forex-scale SHORT angle gate, sweeps
a small stop/target grid on an **in-sample** window, and validates the pick
**out-of-sample**. Writes `tuned_params.json`.

```bash
python retune_atr.py --fetch --range 60d
```

Example run: it calibrated the ATR band to `[2.75, 11.33]` (vs the broken `2.00`
default), found an in-sample optimum (PF ≈ 2.0), but **out-of-sample it flattened
to ≈0 % / PF ≈ 1.0** — so it explicitly warns the params are a *regime fix that
lets the model trade, not a validated edge.* Intraday history is short (~60 days
via Yahoo), so treat all of this as high-variance calibration, **not** proof of
profitability.

**2. Read the current state (`report_state.py`).** Runs the state machine over
the latest bars and reports whether it is SCANNING / ARMED / WINDOW_OPEN (or in a
position), plus the concrete breakout / stop / target levels.

```bash
python report_state.py --fetch                              # default filters
python report_state.py --fetch --params-file tuned_params.json   # with tuned params
python report_state.py --fetch --json                       # machine-readable
```

**Apply tuned params to any run** with `--params-file`:

```bash
python sunrise_ogle_xauusd.py --fetch --params-file tuned_params.json --quiet
```

> These are decision-support readouts of a mechanical model on recent data.
> They are **not financial advice** and **not a vetted live signal**. The
> out-of-sample numbers are the ones that matter, and on this short sample there
> is no demonstrated edge.

## Bring your own CSV

Any CSV with this exact header and column order works:

```
Date,Time,Open,High,Low,Close,Volume
20200821,00:00:00,1952.57,1955.77,1951.61,1955.48,380670
```

`Date` is `%Y%m%d`, `Time` is `%H:%M:%S`, bars are 5-minute. Point the runner at
it and optionally bound the dates:

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
| `--quick-test` | off | Reduce to the last 10 days for a fast smoke test (needs `--todate`). |
| `--plot` | off | Show the Matplotlib chart (needs a display backend). |
| `--quiet` | off | Suppress verbose per-bar debug output. |
| `--no-atr-filter` | off | Disable the regime-specific ATR volatility filters (see calibration note). |
| `--fetch` | off | Download fresh real OHLCV inline before running (overrides `--data`). |
| `--source {yahoo,fmp}` | `yahoo` | Provider for `--fetch`. |
| `--symbol SYM` | `GC=F`/`XAUUSD` | Ticker for `--fetch`. |
| `--range 60d` | `60d` | Yahoo lookback for `--fetch` (≤60d for 5-min bars). |
| `--fmp-api-key KEY` | `$FMP_API_KEY` | Key for `--fetch --source fmp`. |

Strategy parameters (EMA lengths, ATR multipliers, pullback depth, window
periods, ATR volatility filters, …) remain as module-level constants and a
`params` dict at the top of `sunrise_ogle_xauusd.py`; edit there to tune the
strategy, exactly as upstream.

## Offline / no network

If you can't reach a data provider, generate a deterministic synthetic feed
instead (a random walk — it only proves the pipeline runs, not anything about
the strategy's edge):

```bash
python generate_sample_data.py                                   # data/XAUUSD_5m_sample.csv
python sunrise_ogle_xauusd.py --data data/XAUUSD_5m_sample.csv --quiet
```

## Runtime outputs

With trade reporting enabled (default), per-run trade logs are written to a
`temp_reports/` directory relative to your working directory. Both `data/*.csv`
and `temp_reports/` are git-ignored.
