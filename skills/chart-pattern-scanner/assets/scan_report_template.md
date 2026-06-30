# Candlestick Pattern Scan: [SYMBOL]

**Date:** [YYYY-MM-DD]
**Timeframe:** [daily / weekly / intraday]
**Source:** [user-provided chart image / generated from OHLCV (`generate_candle_chart.py`)]

---

## Signal Summary

| Field | Value |
|---|---|
| **Overall Signal** | **[BUY / SELL / NEUTRAL]** |
| **Confidence** | [High / Medium / Low] |
| **Net Score** | [+/- X.XX] |
| **Trend Context** | [Uptrend / Downtrend / Range] |

**One-line read:** [e.g., "Bullish engulfing at tested support on rising volume — BUY, medium confidence."]

---

## Detected Patterns

| Candle / Date | Pattern | Signal | Reliability | Location | Notes |
|---|---|---|---|---|---|
| [date] | [pattern name] | [bullish/bearish/neutral] | [0–1] | [at support / mid-range / ...] | [observation] |

> Cross-check: deterministic detector (`detect_candlestick_patterns.py`) reported
> **[BUY/SELL/NEUTRAL]** (score [X.XX]). [Agrees with / differs from] the visual
> read because [reason].

---

## Trend & Location Analysis

- **Trend:** [description of trend leading into the latest candle]
- **Key support:** [level(s)]
- **Key resistance:** [level(s)]
- **Latest pattern location:** [relationship to S/R and trend]
- **Volume confirmation:** [present / absent / divergent]

---

## Actionable Plan

| | Level | Rationale |
|---|---|---|
| **Entry trigger** | [price] | [e.g., break of signal candle high] |
| **Invalidation / stop** | [price] | [level that disproves the pattern] |
| **First target** | [price] | [nearest S/R or measured move] |
| **Reward : Risk** | [X.X : 1] | |

---

## Caveats

- [Chart quality / resolution limitations]
- [Conflicting signals or higher-timeframe disagreement]
- [Anything that lowers confidence]

---

*Disclaimer: This analysis is for informational and educational purposes only and
does not constitute financial advice. Candlestick patterns express probabilities,
not certainties. Always apply independent risk management.*
