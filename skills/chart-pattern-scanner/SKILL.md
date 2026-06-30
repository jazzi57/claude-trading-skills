---
name: chart-pattern-scanner
description: This skill should be used when scanning candlestick charts for classic patterns (engulfing, hammer, doji, morning/evening star, three soldiers/crows, etc.) and converting them into a Buy/Sell/Neutral trading signal. Use it when the user provides a candlestick chart image, asks "what does this chart say / scan this chart", wants candlestick pattern detection for a stock or crypto ticker, or wants to generate a candlestick chart from OHLCV data and have it analyzed. Inspired by the ChartScanAI YOLOv8 detector, adapted to vision-based reading plus a deterministic rule-based cross-check. All analysis and output are in English.
---

# Chart Pattern Scanner

## Overview

This skill scans candlestick charts to detect classic single-, double-, and
triple-candle patterns and classify the current setup as **BUY**, **SELL**, or
**NEUTRAL** with a confidence level. It is an LLM adaptation of the
[ChartScanAI](https://github.com/Omar-Karimov/ChartScanAI) project, which uses a
YOLOv8 object-detection model to localize candlestick formations and label them
Buy/Sell. Here, pattern recognition is performed two ways that cross-check each
other:

1. **Vision-based reading** — Claude reads the chart image against a documented
   pattern catalog and signal-classification framework.
2. **Deterministic detection** — a rule-based Python script
   (`detect_candlestick_patterns.py`) computes patterns directly from OHLCV data,
   providing an objective second opinion.

The skill works on user-provided chart images, on OHLCV CSV data, or on a ticker
(when `yfinance` is available, via `generate_candle_chart.py`).

## When to Use

- User provides a candlestick chart image and asks for pattern detection or a Buy/Sell read
- User asks "scan this chart" / "what candlestick patterns do you see?"
- User wants a candlestick signal for a stock or crypto ticker
- User has OHLCV data (CSV) and wants pattern detection + a chart
- User wants an objective, reproducible candlestick scan to cross-check a visual read

Do NOT use this skill when:
- The user wants full multi-factor technical analysis (trend, MAs, volume,
  scenarios) → use `technical-analyst`
- The user wants market-breadth chart analysis → use `breadth-chart-analyst`
- The user wants fundamental screening → use a screener skill

## Prerequisites

- **Input**: a candlestick chart image, an OHLCV CSV, or a ticker symbol
- **No API keys required**: image analysis and the deterministic detector work
  offline. Ticker fetch is optional and uses `yfinance` (no key) when installed.
- **Optional Python deps**: `yfinance` (ticker fetch), `mplfinance`/`matplotlib`
  (chart rendering). The deterministic detector uses only the standard library.

## Output

Markdown scan reports saved to the `reports/` directory:
- **File format**: `[SYMBOL]_pattern_scan_[YYYY-MM-DD].md`
- The deterministic detector can also emit a `.json` report
  (`[SYMBOL]_pattern_scan_[YYYY-MM-DD].json`) with `--output-dir`.

## Core Principles

1. **Patterns are hypotheses; location and confirmation make them signals** — never call a direction from candle shape alone.
2. **Cross-check vision with rules** — reconcile the visual read against the deterministic detector and explain any disagreement.
3. **Latest bar is decisive** — the current signal reflects patterns completing on the most recent candle; older patterns are context.
4. **State confidence honestly** — low-quality charts and ambiguous setups get lower confidence, explicitly.
5. **Always frame risk** — every actionable signal includes an entry trigger, invalidation level, and target.

## Workflow

### Step 1: Identify the Input and Prepare Data

Determine what the user supplied:

- **Chart image** → proceed to vision analysis (Step 3). If OHLCV is also
  available, run the deterministic detector for cross-check.
- **OHLCV CSV** → run the deterministic detector (Step 2); optionally render a
  chart for the user with `generate_candle_chart.py`.
- **Ticker symbol** → generate a chart and (if data is accessible) run the
  detector:

```bash
# Render a candlestick chart from a ticker (needs yfinance + mplfinance/matplotlib)
python3 skills/chart-pattern-scanner/scripts/generate_candle_chart.py \
  --ticker AAPL --period 6mo --interval 1d --output-dir reports/

# Or render from a local OHLCV CSV (no network)
python3 skills/chart-pattern-scanner/scripts/generate_candle_chart.py \
  --csv path/to/AAPL.csv --output-dir reports/
```

### Step 2: Run the Deterministic Detector (when OHLCV is available)

```bash
python3 skills/chart-pattern-scanner/scripts/detect_candlestick_patterns.py \
  --csv path/to/AAPL.csv --ticker AAPL --output-dir reports/ --json
```

The CSV must have (case-insensitive) `open, high, low, close` columns; `date`
and `volume` are optional. The script prints every detected pattern
chronologically plus an aggregated **BUY / SELL / NEUTRAL** signal, score, and
confidence. Record these as the objective baseline.

### Step 3: Load the Knowledge Base

Before reading a chart visually, read both references:

```
Read: references/candlestick_pattern_catalog.md       # pattern geometry + reliability
Read: references/signal_classification_framework.md   # trend/location/confirmation → signal
```

### Step 4: Read the Chart Visually

Working from the chart image (give special attention to the **rightmost / most
recent candles**):

1. **Trend context** — classify the trend leading into the latest candle
   (uptrend / downtrend / range).
2. **Support & resistance** — mark the nearest tested levels.
3. **Pattern detection** — scan for catalog patterns, focusing on completions on
   the latest 1–3 candles. Note each pattern, its signal, and its location.
4. **Confirmation** — assess volume and any follow-through.
5. **Classify** — apply the signal-classification framework to produce a net
   score and a BUY / SELL / NEUTRAL call with confidence.

### Step 5: Reconcile Vision vs. Deterministic

If both a visual read and the deterministic detector are available:
- When they **agree**, state the signal with the combined confidence.
- When they **differ**, investigate (the detector may miss location/volume
  nuance; the eye may misjudge a body/shadow ratio). Explain the discrepancy and
  decide which to trust, lowering confidence accordingly.

### Step 6: Generate the Report

Use the template and save to `reports/`:

```
Read and use as template: assets/scan_report_template.md
```

Save as `[SYMBOL]_pattern_scan_[YYYY-MM-DD].md`. Include: signal summary,
detected-patterns table, trend/location analysis, the deterministic cross-check,
an actionable plan (entry/stop/target with reward:risk), caveats, and the
disclaimer.

## Quality Standards

- **Specificity**: cite actual price levels for entry, stop, and target — never vague descriptions.
- **Recency**: the headline signal must reflect the latest candle, not stale history.
- **Objectivity**: report patterns that are present, including ones that conflict with the headline call.
- **Confidence calibration**: ambiguous, low-resolution, or volume-less charts → lower confidence, stated plainly.
- **Risk framing**: every actionable signal includes invalidation and target.
- **Disclaimer**: every report ends with the not-financial-advice disclaimer.

## Example Usage

**Example 1 — Scan a chart image**
```
User: "Scan this BTC daily chart." [uploads image]
Scanner:
1. Reads the two references
2. Identifies downtrend into a hammer at support with a confirming up close
3. Calls BUY (medium confidence), entry above hammer high, stop below hammer low
4. Saves BTC_pattern_scan_2026-06-20.md
```

**Example 2 — Scan from OHLCV CSV**
```
User: "Here's AAPL OHLCV — what's the candlestick signal?" [provides CSV]
Scanner:
1. Runs detect_candlestick_patterns.py --csv aapl.csv --ticker AAPL --json
2. Detector reports bearish engulfing on the latest bar → SELL (medium)
3. Renders a chart with generate_candle_chart.py for visual confirmation
4. Reconciles, writes AAPL_pattern_scan_2026-06-20.md
```

**Example 3 — Scan a ticker**
```
User: "Scan NVDA for candlestick patterns."
Scanner:
1. generate_candle_chart.py --ticker NVDA --period 6mo  (if yfinance available)
2. Reads the rendered chart + runs the detector on the same data
3. Produces a BUY/SELL/NEUTRAL signal with an actionable plan
```

## Resources

### references/candlestick_pattern_catalog.md
Geometry, required context, signal, and reliability prior for every supported
single-, double-, and triple-candle pattern. Read before any visual scan.

### references/signal_classification_framework.md
Decision logic that turns detected patterns into a BUY/SELL/NEUTRAL signal via
trend context, location scoring, confirmation, thresholds, and conflict
resolution.

### scripts/detect_candlestick_patterns.py
Deterministic, standard-library-only pattern detector. Reads an OHLCV CSV and
outputs detected patterns plus an aggregated signal (text or JSON).

### scripts/generate_candle_chart.py
Renders a candlestick chart PNG from a ticker (`yfinance`) or an OHLCV CSV, using
`mplfinance` when available with a `matplotlib` fallback.

### scripts/fetch_dfm_official.py
Optional regional data adapter: fetches **official Dubai Financial Market (DFM)**
daily OHLC from the exchange's public widget API (`api2.dfm.ae`) and writes
per-symbol OHLCV CSVs that feed `detect_candlestick_patterns.py` /
`generate_candle_chart.py`. Scrapes the public API key from dfm.ae at runtime
(nothing hardcoded). Pure parsing/series logic is unit-tested offline.

```bash
python3 skills/chart-pattern-scanner/scripts/fetch_dfm_official.py \
  --from 2026-01-01 --to 2026-06-19 --output-dir reports/dfm_official/
```

### scripts/scan_dfm_market.py
One-command DFM pipeline: **refresh official data → scan every stock → write a
consolidated report (+ optional charts)**. Chains `fetch_dfm_official`,
`detect_candlestick_patterns`, and `generate_candle_chart`. Pure scan/report
logic is unit-tested offline.

```bash
python3 skills/chart-pattern-scanner/scripts/scan_dfm_market.py \
  --from 2026-03-01 --to 2026-06-19 --charts --output-dir reports/dfm_official/
```

### scripts/daily_dfm_signals.py
The **daily actionable-signal runner**: from a freshly-ingested bulletin series
it reports only the two edges the backtest validated — the EMAAR~EMAARDEV spread
z-score (relative-value state) and a scan of every symbol's most recent bar(s)
for a **high-volume** hanging_man / shooting_star reversal. Deliberately silent
on everything else (no validated edge). Writes `DFM_daily_signals.{md,json}`.
Pure logic unit-tested.

```bash
python3 skills/chart-pattern-scanner/scripts/daily_dfm_signals.py \
  --series-json reports/dfm_bulletin/_all_series.json --within 1 --output-dir reports/
```

Schedule it daily with `scripts/run_dfm_daily_signals.sh` (refreshes API history,
prefers a volume-accurate bulletin if present) and
`launchd/com.trade-analysis.dfm-daily-signals.plist`.

### scripts/ingest_ohlcv.py
Ingest an arbitrary OHLCV export (iVestor / broker / Excel / CSV — single- or
multi-symbol, flexible column names) into the `_all_series.json` format the
backtester and scanner consume. Use it to bring in deeper history than the free
DFM API serves. Reads the **official DFM trading bulletin** natively
(`report_date` / `current_close` / `last_price` / `trade_volume` columns;
untraded `O=H=L=0` sessions are dropped), so a downloaded bulletin gives real
OHLC **plus share volume** back to 2024.

```bash
python3 skills/chart-pattern-scanner/scripts/ingest_ohlcv.py \
  exports/ --output-dir reports/dfm_history/
```

### scripts/daily_limit.py
DFM daily price-limit (circuit band) helpers — the ±15% cap on how far an
ordinary share can move in one session. Computes the reachable band, whether a
target is fillable today, and the **minimum sessions** a stop/target needs under
the compounding cap (so 2R targets aren't mislabelled as one-day moves). Pure +
unit-tested.

### scripts/correlation_study.py
Non-candlestick structural study of a multi-symbol series: per-stock lag-1
return autocorrelation (mean-reversion vs momentum), beta to an equal-weight
market factor, market→stock lead-lag, and the most-correlated pairs
(pair-trade candidates). Pure logic unit-tested.

```bash
python3 skills/chart-pattern-scanner/scripts/correlation_study.py \
  --series-json reports/dfm_history/_all_series.json
```

### scripts/single_stock_strategy.py
A dedicated, backtested **single-stock trading mechanism** (built for Air Arabia).
Two long-only modes — `trend` (SMA trend-follow, suits trending names) and
`meanrev` (RSI dip-buy) — each backtested on the stock's own history with a
buy-&-hold benchmark, plus the current signal. Pure logic unit-tested.

```bash
python3 skills/chart-pattern-scanner/scripts/single_stock_strategy.py \
  --symbol AIRARABIA --mode trend
```

### scripts/pairs_strategy.py
A backtested **pairs / relative-value (spread) strategy** for two co-moving
symbols (built for the strongest DFM pair, **EMAAR ~ EMAARDEV**). Z-scores the
log price ratio over a trailing window; enters when the ratio is stretched
(|z| ≥ entry), exits on reversion or a divergence stop. Reports trades,
win-rate, market-neutral P&L, and the current signal. `--scan` ranks every
correlated pair in the series for tradable spreads (with a multiple-comparison
warning — candidates to investigate, not proven edges). Pure logic unit-tested.
(Note the DFM retail short constraint flagged in its output.)

```bash
# one configured pair
python3 skills/chart-pattern-scanner/scripts/pairs_strategy.py \
  --series-json reports/dfm_bulletin/_all_series.json --a EMAAR --b EMAARDEV

# scan the whole universe for candidate spreads
python3 skills/chart-pattern-scanner/scripts/pairs_strategy.py \
  --series-json reports/dfm_bulletin/_all_series.json --scan --min-corr 0.4
```

### scripts/backtest_patterns.py
Backtests the detector's candlestick patterns on historical OHLCV to produce
**empirical hit-rates** (sample size, % resolving in the pattern's direction at
each forward horizon, average directional return) — replacing heuristic
probabilities with evidence from the market's own history. With
`--volume-confirmation` it also splits each pattern by event-bar volume
(high ≥ 1.5× the prior 20-bar average vs normal) to test whether volume sharpens
the edge. Pure stats logic is unit-tested offline.

```bash
python3 skills/chart-pattern-scanner/scripts/backtest_patterns.py \
  --series-json reports/dfm_bulletin/_all_series.json --horizons 5,10 \
  --volume-confirmation --output-dir reports/
```

### assets/scan_report_template.md
Structured report template for the scan output.

## Attribution

Inspired by [ChartScanAI](https://github.com/Omar-Karimov/ChartScanAI) by Omar
Karimov (YOLOv8 + Streamlit candlestick pattern detector). This skill
reimplements the *concept* — candlestick pattern detection and Buy/Sell
classification — using Claude's vision plus a rule-based detector, with no
dependency on the original trained model.
