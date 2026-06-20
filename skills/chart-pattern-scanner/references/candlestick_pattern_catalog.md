# Candlestick Pattern Catalog

This catalog is the knowledge base for visual candlestick pattern recognition.
It mirrors the classes a trained object detector (such as the YOLOv8 model in
ChartScanAI) learns to localize on a chart, expressed as explicit geometric
criteria so they can be identified from a chart image OR from OHLCV data.

For each pattern: **definition**, **geometry**, **context required**, **signal**
(bullish / bearish / neutral), and a **reliability** prior (0–1) reflecting how
often the pattern resolves in its expected direction. Reliability is a *prior*,
not a guarantee — always weight it by location and confirmation (see
`signal_classification_framework.md`).

Terminology:
- **Body** = |close − open|. **Range** = high − low.
- **Upper shadow** = high − max(open, close). **Lower shadow** = min(open, close) − low.
- A **bullish** candle closes above its open; a **bearish** candle closes below.

---

## 1. Single-Candle Patterns

### Doji (neutral, 0.30)
- **Geometry**: Body ≤ 10% of range. Open ≈ close.
- **Meaning**: Indecision / equilibrium. Significance depends entirely on
  location — a doji at the top of an extended uptrend or bottom of a downtrend
  warns of a possible reversal; mid-range it is noise.
- **Variants**: Long-legged doji (long shadows both sides), gravestone doji
  (long upper shadow, open=close=low → bearish), dragonfly doji (long lower
  shadow, open=close=high → bullish).

### Hammer (bullish, 0.60)
- **Geometry**: Small body in the **upper** third; lower shadow ≥ 2× body;
  little or no upper shadow.
- **Context**: Must appear **after a downtrend**.
- **Meaning**: Sellers drove price down intraday but buyers reclaimed the close.
  Bottom-reversal signal; stronger on high volume and with a confirming up close.

### Hanging Man (bearish, 0.50)
- **Geometry**: Identical to a hammer (small body up top, long lower shadow).
- **Context**: Appears **after an uptrend**.
- **Meaning**: First sign that buyers are losing control. Needs bearish
  confirmation the next bar.

### Inverted Hammer (bullish, 0.50)
- **Geometry**: Small body in the **lower** third; upper shadow ≥ 2× body;
  little lower shadow.
- **Context**: After a downtrend → potential bottom reversal (needs confirmation).

### Shooting Star (bearish, 0.60)
- **Geometry**: Same shape as inverted hammer (small body at bottom, long upper
  shadow).
- **Context**: After an uptrend → top reversal. Rejection of higher prices.

### Marubozu (directional, 0.55)
- **Geometry**: Body ≥ 90% of range; negligible shadows.
- **Bullish marubozu**: full green body — strong buying conviction / continuation.
- **Bearish marubozu**: full red body — strong selling conviction / continuation.

### Spinning Top (neutral, 0.30)
- **Geometry**: Small body with upper and lower shadows both larger than the
  body. Indecision; often precedes consolidation or reversal in context.

---

## 2. Double-Candle Patterns

### Bullish Engulfing (bullish, 0.70)
- **Geometry**: A small bearish candle followed by a larger bullish candle whose
  body **fully engulfs** the prior body (open ≤ prior close, close ≥ prior open).
- **Context**: After a downtrend. One of the most reliable two-bar reversals.

### Bearish Engulfing (bearish, 0.70)
- **Geometry**: A small bullish candle followed by a larger bearish candle that
  engulfs it (open ≥ prior close, close ≤ prior open).
- **Context**: After an uptrend → top reversal.

### Piercing Line (bullish, 0.60)
- **Geometry**: Prior bearish candle; next opens **below the prior low** (gap
  down) then rallies to close **above the midpoint** of the prior body (but
  below the prior open).
- **Context**: Downtrend. Less powerful than engulfing but a solid bottom signal.

### Dark Cloud Cover (bearish, 0.60)
- **Geometry**: Prior bullish candle; next opens **above the prior high** then
  sells off to close **below the midpoint** of the prior body.
- **Context**: Uptrend → top reversal.

### Bullish Harami (bullish, 0.45)
- **Geometry**: Large bearish candle followed by a small bullish candle whose
  body is **contained inside** the prior body.
- **Meaning**: Momentum stalling; needs confirmation. ("Harami" = pregnant.)

### Bearish Harami (bearish, 0.45)
- **Geometry**: Large bullish candle followed by a small bearish candle inside
  the prior body. Uptrend exhaustion warning.

### Tweezer Bottom (bullish, 0.40)
- **Geometry**: Two adjacent candles with **matching lows** at the end of a
  downtrend (typically bearish then bullish). Support held twice.

### Tweezer Top (bearish, 0.40)
- **Geometry**: Two adjacent candles with **matching highs** at the end of an
  uptrend. Resistance rejected twice.

---

## 3. Triple-Candle Patterns

### Morning Star (bullish, 0.75)
- **Geometry**: (1) Large bearish candle; (2) small-bodied candle that gaps
  down (the "star"); (3) large bullish candle closing **above the midpoint** of
  candle 1.
- **Context**: Downtrend. High-reliability three-bar bottom reversal.

### Evening Star (bearish, 0.75)
- **Geometry**: (1) Large bullish candle; (2) small star gapping up; (3) large
  bearish candle closing **below the midpoint** of candle 1.
- **Context**: Uptrend. High-reliability top reversal.

### Three White Soldiers (bullish, 0.70)
- **Geometry**: Three consecutive long bullish candles, each opening within the
  prior body and closing at a new local high.
- **Meaning**: Strong, sustained buying — bottom reversal or breakout
  continuation. Beware if candles are over-extended (overbought).

### Three Black Crows (bearish, 0.70)
- **Geometry**: Three consecutive long bearish candles, each opening within the
  prior body and closing at a new local low.
- **Meaning**: Strong, sustained selling — top reversal or breakdown continuation.

---

## 4. Pattern Reliability Summary

| Pattern | Signal | Reliability | Required context |
|---|---|---|---|
| Morning Star | Bullish | 0.75 | Downtrend |
| Evening Star | Bearish | 0.75 | Uptrend |
| Bullish Engulfing | Bullish | 0.70 | Downtrend |
| Bearish Engulfing | Bearish | 0.70 | Uptrend |
| Three White Soldiers | Bullish | 0.70 | After decline / base |
| Three Black Crows | Bearish | 0.70 | After advance / top |
| Hammer | Bullish | 0.60 | Downtrend |
| Shooting Star | Bearish | 0.60 | Uptrend |
| Piercing Line | Bullish | 0.60 | Downtrend |
| Dark Cloud Cover | Bearish | 0.60 | Uptrend |
| Marubozu | Directional | 0.55 | Any (continuation) |
| Hanging Man | Bearish | 0.50 | Uptrend |
| Inverted Hammer | Bullish | 0.50 | Downtrend |
| Bullish/Bearish Harami | Reversal | 0.45 | Trend exhaustion |
| Tweezer Top/Bottom | Reversal | 0.40 | At S/R |
| Doji / Spinning Top | Neutral | 0.30 | Context-dependent |

**Golden rule**: A candlestick pattern is only as good as its **location**. The
same hammer is high-value at established support after a decline and worthless in
the middle of a range. Always read patterns together with trend and
support/resistance, never in isolation.
