# Signal Classification Framework

How to convert detected candlestick patterns into a single, actionable
**BUY / SELL / NEUTRAL** signal with a confidence level. This is the
decision logic ChartScanAI compresses into its Buy/Sell class head, made
explicit so it can be applied by vision OR by the deterministic detector
(`scripts/detect_candlestick_patterns.py`).

## Core Principle

> A pattern is a *hypothesis*. Location and confirmation turn it into a *signal*.

Never issue a directional call from pattern shape alone. Combine three factors:

1. **Pattern** — what formed, and its reliability prior (see the catalog).
2. **Location** — where it formed relative to trend and support/resistance.
3. **Confirmation** — volume and follow-through on the next candle.

## Step 1 — Establish the Trend Context

Classify the prevailing trend leading into the most recent candle:

- **Uptrend** — higher highs / higher lows; price above rising moving averages.
- **Downtrend** — lower highs / lower lows; price below falling moving averages.
- **Range / flat** — no persistent slope.

Reversal patterns only count when they oppose an existing trend (a hammer in a
downtrend; a shooting star in an uptrend). A "bullish" pattern inside an
established uptrend is continuation, not reversal — weight it lower.

## Step 2 — Score the Location

Assign a location multiplier to each detected pattern:

| Location | Multiplier | Rationale |
|---|---|---|
| At a tested support (bullish) / resistance (bearish) | ×1.3 | Confluence |
| At a round number / prior swing pivot | ×1.15 | Memory level |
| Mid-range, no nearby level | ×0.7 | Low conviction |
| Against the dominant higher-timeframe trend | ×0.6 | Counter-trend |

## Step 3 — Apply Confirmation

| Confirmation factor | Adjustment |
|---|---|
| Above-average volume on the signal candle | +0.10 |
| Next candle closes in the signal's direction | +0.15 |
| Gap in the signal's direction | +0.10 |
| Low volume / no follow-through | −0.10 |

## Step 4 — Aggregate to a Signal

For the **most recent candle**, sum the signed, weighted contributions of every
pattern completing on it:

```
contribution = reliability × location_multiplier ± confirmation_adjustments
score = Σ contributions   (bullish positive, bearish negative)
```

The deterministic script uses a simplified version of this: it makes the signal
decisive on patterns completing on the latest bar (with prior-window patterns as
decayed context) and reports a net score. When reading a chart visually, apply
the full table above for a more nuanced score.

### Thresholds

| Net score | Signal | Confidence |
|---|---|---|
| ≥ +1.0 | **BUY** | High |
| +0.5 to +1.0 | **BUY** | Medium |
| 0 to +0.5 | NEUTRAL (bullish lean) | Low |
| −0.5 to 0 | NEUTRAL (bearish lean) | Low |
| −1.0 to −0.5 | **SELL** | Medium |
| ≤ −1.0 | **SELL** | High |

## Step 5 — Risk Framing (always include)

Every actionable signal must state:

- **Entry trigger** — e.g., "break above the signal candle high".
- **Invalidation / stop** — e.g., "below the hammer low"; the level that proves
  the pattern wrong.
- **First target** — nearest resistance (long) or support (short), or a measured
  move; express reward:risk.

## Conflict Resolution

- **Latest bar wins.** A fresh completion on the most recent candle overrides
  stale patterns earlier in the window.
- **Higher timeframe wins ties.** If daily says BUY and weekly says SELL, reduce
  confidence and prefer the higher timeframe's bias.
- **When patterns cancel** (a bullish and bearish of similar weight), report
  NEUTRAL and explain the conflict rather than forcing a call.

## Honesty Requirements

- State confidence explicitly; never present a low-confidence read as certainty.
- If the chart is ambiguous, low-resolution, or lacks volume, say so and lower
  confidence accordingly.
- This is informational analysis, **not financial advice** (carry the disclaimer
  into every report).
