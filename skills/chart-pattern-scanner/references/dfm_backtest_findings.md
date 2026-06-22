# DFM Candlestick Backtest — Findings & Methodology

Empirical study of the chart-pattern-scanner's candlestick patterns on the
Dubai Financial Market (DFM). Produced from official DFM EOD data; preserved
here because the generated reports themselves are not committed.

## Dataset
- **Source:** official DFM widget API (`api2.dfm.ae`, `SearchCompanyPrices`), via `fetch_dfm_official.py`.
- **Coverage:** **71 symbols, ~19,650 daily bars, 2025-01-02 → 2026-06-19** (≈18 months).
- **Limit:** the public API clamps anything before ~Jan 2025 to a frozen placeholder, so deeper history is not available from this source. The window is therefore **a single market regime** (a net down-drift).

## Method
For every occurrence of each pattern across all symbols, measure the
**close-to-close forward outcome** at 5- and 10-day horizons (`backtest_patterns.py`),
then compare the **hit-rate** (% that resolved in the pattern's expected
direction) against the market **base rate** and test significance.

- **Base rate (5d):** P(up) = **45%**, P(down) = **55%** — the tape drifted down, which inflates raw bearish hit-rates and depresses bullish ones.
- **Lift** = hit-rate − base rate. **z** = (hit − base) / SE; |z| ≥ 2 ≈ 95% significant.

## Key findings (5-day horizon)

| Pattern | Dir | n | Hit | Base | Lift | z | Verdict |
|---|---|---|---|---|---|---|---|
| hanging_man | bearish | 502 | 60% | 55% | **+5.6%** | **+2.5** | **Edge (significant)** |
| inverted_hammer | bullish | 362 | 49% | 45% | +4.2% | +1.6 | weak/none |
| bearish_engulfing | bearish | 759 | 50% | 55% | −4.9% | −2.7 | **Contrarian (fade)** |
| bullish_engulfing | bullish | 698 | 40% | 45% | −5.7% | −3.0 | **Contrarian** |
| bullish_marubozu | bullish | 1733 | 38% | 45% | −6.8% | −5.7 | **Contrarian** |
| tweezer_top | bearish | 217 | 47% | 55% | −7.3% | −2.2 | **Contrarian** |
| shooting_star | bearish | 260 | 47% | 55% | −7.9% | −2.5 | **Contrarian** |
| tweezer_bottom | bullish | 201 | 36% | 45% | −8.9% | −2.5 | **Contrarian** |
| bearish_marubozu | bearish | 1577 | 44% | 55% | −10.5% | −8.4 | **Contrarian (strong)** |

*(Patterns near zero lift / |z|<2 — three_white_soldiers, hammer, morning_star, harami, etc. — show no usable edge.)*

## Conclusions
1. **Candlestick patterns are not a reliable standalone edge on DFM.** Most bullish patterns hit below the 45% base rate; raw bearish "wins" are mostly the down-drift, not signal.
2. **Only `hanging_man` shows a statistically significant positive edge** (bearish, +5.6% lift) — useful as a short/exit trigger.
3. **DFM mean-reverts against momentum extremes.** `bearish_marubozu`, `bullish_marubozu`, `tweezer_bottom`, and the engulfing patterns have large *negative* lift — price tends to reverse *against* the pattern within a week. The data-backed play is to **fade** an over-extended single-direction candle, not to chase it.
4. **Respect the asymmetric daily price limit** (`daily_limit.py`): since **~March 2026** DFM caps a session at **+15% up / −5% down** (the downside was tightened). Verified here: down-days beyond −5% run ~30–50/month through Feb 2026, then collapse to **1 (Mar), 1 (Apr), 0 (May), 0 (Jun)**, while +15% up-days persist. Implication: **short targets fill slowly** — a −13% objective needs ~3 sessions, and the most a name can fall tomorrow is −5%. The feed does not expose per-stock limits, so +15%/−5% is the default assumption (a few boards/securities may differ).

## Out-of-sample note (2026-06-22)
On the first day after the study window, the two edges pointed the right way:
`hanging_man` shorts fell 3 of 4; the "fade the bearish pattern" names rose 5 of 9
(led by Emirates NBD +1.9%). One day is not significant — directional confirmation only.

## Limitations
- **Single regime** (18 months, net down-drift) — edges may not hold in a bull phase. A multi-year sample (paid vendor or broker export, via `ingest_ohlcv.py`) would test robustness.
- **Volume** is a trade-count proxy (the DFM widget API omits share volume), so volume-confirmation could not be tested.
- Outcomes are **close-to-close**, ignoring intraday paths, slippage, and trading costs.

*Informational/educational only — not financial advice. Past behaviour does not guarantee future results.*
