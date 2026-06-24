---
layout: default
title: "Chart Pattern Scanner"
grand_parent: English
parent: Skill Guides
nav_order: 13
lang_peer: /ja/skills/chart-pattern-scanner/
permalink: /en/skills/chart-pattern-scanner/
generated: true
---

# Chart Pattern Scanner
{: .no_toc }

This skill should be used when scanning candlestick charts for classic patterns (engulfing, hammer, doji, morning/evening star, three soldiers/crows, etc.) and converting them into a Buy/Sell/Neutral trading signal. Use it when the user provides a candlestick chart image, asks "what does this chart say / scan this chart", wants candlestick pattern detection for a stock or crypto ticker, or wants to generate a candlestick chart from OHLCV data and have it analyzed. Inspired by the ChartScanAI YOLOv8 detector, adapted to vision-based reading plus a deterministic rule-based cross-check. All analysis and output are in English.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/chart-pattern-scanner){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

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

---

## 2. When to Use

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

---

## 3. Prerequisites

- **Input**: a candlestick chart image, an OHLCV CSV, or a ticker symbol
- **No API keys required**: image analysis and the deterministic detector work
  offline. Ticker fetch is optional and uses `yfinance` (no key) when installed.
- **Optional Python deps**: `yfinance` (ticker fetch), `mplfinance`/`matplotlib`
  (chart rendering). The deterministic detector uses only the standard library.

---

## 4. Quick Start

```bash
# Render a candlestick chart from a ticker (needs yfinance + mplfinance/matplotlib)
python3 skills/chart-pattern-scanner/scripts/generate_candle_chart.py \
  --ticker AAPL --period 6mo --interval 1d --output-dir reports/

# Or render from a local OHLCV CSV (no network)
python3 skills/chart-pattern-scanner/scripts/generate_candle_chart.py \
  --csv path/to/AAPL.csv --output-dir reports/
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/chart-pattern-scanner/references/candlestick_pattern_catalog.md`
- `skills/chart-pattern-scanner/references/dfm_backtest_findings.md`
- `skills/chart-pattern-scanner/references/signal_classification_framework.md`

**Scripts:**

- `skills/chart-pattern-scanner/scripts/backtest_patterns.py`
- `skills/chart-pattern-scanner/scripts/daily_limit.py`
- `skills/chart-pattern-scanner/scripts/detect_candlestick_patterns.py`
- `skills/chart-pattern-scanner/scripts/fetch_dfm_official.py`
- `skills/chart-pattern-scanner/scripts/generate_candle_chart.py`
- `skills/chart-pattern-scanner/scripts/ingest_ohlcv.py`
- `skills/chart-pattern-scanner/scripts/scan_dfm_market.py`
- `skills/chart-pattern-scanner/scripts/single_stock_strategy.py`
