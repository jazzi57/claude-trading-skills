# Gulf Markets Swing Screener (DFM / ADX)

Swing-trade screening for **Dubai Financial Market (DFM)** and **Abu Dhabi
Securities Exchange (ADX)** equities, sized for a given account and risk budget.

It finds stocks biased to rise (confirmed uptrend near a breakout), then prints a
**buy (entry), sell-target, and stop** for each, with a risk-based share count.
Stocks that aren't set up are reported as no-trade with a reason — no invented levels.

## Data availability (important)

| Market | Snapshot | Daily history | Source used |
|---|---|---|---|
| **DFM** | ✅ official `api2.dfm.ae/mw/v1/stocks` | ✅ Yahoo `<SYM>.AE` (validated identical to DFM's official `SearchCompanyPrices` feed) | `--source yahoo` |
| **ADX** | ✅ official `apigateway.adx.ae/.../securityOverview/<SYM>` (incl. 52-week range) | ❌ not public — daily chart is behind a WAF-protected proxy; Yahoo has **no** ADX coverage | `--source adx-official` (52w-aware) |
| **Both** | — | ✅ via vendor | `--source twelvedata` (needs `TWELVEDATA_API_KEY`) |

So DFM gets a full **true-ATR / trend-template** screen today. ADX is **52-week
positioning** (snapshot only) until a vendor key is supplied — then it gets the
same true-ATR treatment.

## Usage

```bash
# DFM — full main board, true-ATR via Yahoo
python3 scripts/run_screen.py --market dfm --source yahoo --account 20000 --risk 1.0

# ADX — 52-week-aware via the official snapshot feed
python3 scripts/run_screen.py --market adx --source adx-official --account 20000

# Either market with full daily history via Twelve Data (covers ADX + DFM)
export TWELVEDATA_API_KEY=your_data_key   # NOT a brokerage login
python3 scripts/run_screen.py --market adx --source twelvedata --account 20000
```

Reports are written to `reports/<market>_swing_<date>.md` and `.json`.

## Method

- **Entry:** break of the recent pivot / session high (`max(close, 20-day high)`).
- **Stop:** `entry − 2×ATR(14)` when daily history exists; otherwise a
  volatility-adaptive 5–12% stop from the session range.
- **Target:** 2R (twice the per-share risk).
- **Sizing:** risk `--risk`% of `--account` per trade, capped at `--max-pos`% of
  the account per position.

## Notes / limits

- All prices are **delayed** official-feed data — confirm levels at your broker.
- These are rule-based screens, **not predictions or advice**.
- The ADX market-watch key is the public one embedded in ADX's own website; it is
  used only to read the same delayed public data a browser sees.

## Tests

```bash
python3 -m pytest scripts/tests/ -q
```
