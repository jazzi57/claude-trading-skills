# Test Coverage Analysis — 2026-07-06

Audit of the repository's automated test coverage: what is measured, what is
silently skipped, and where new tests would pay off most. Numbers come from a
full local run (`uv run --extra dev pytest --cov=skills --cov=scripts`,
Python 3.11): **3,425 tests collected, 3,408 passed, 17 skipped, 86.0% line
coverage of measured files**.

The headline number is misleadingly healthy: roughly **18,000 LOC of skill
scripts were never imported by any executed test**, so they do not appear in
the coverage denominator at all. The biggest wins here are not "write more
unit tests" but "run the tests we already have, everywhere" and "cover the
untested monoliths".

---

## 1. Execution gaps — tests exist but are not run (highest priority)

### 1.1 CI runs only 20 of 50 tested skills

`.github/workflows/ci.yml` enumerates per-skill pytest steps by hand. 50
skills have test suites; only 20 (plus `scripts/tests/`) have a CI step.
These 30 tested skills are **never executed in CI** (only locally via the
pre-push hook):

breadth-chart-analyst, breakout-trade-planner, canslim-screener,
dividend-growth-pullback-screener, downtrend-duration-analyzer,
earnings-calendar, earnings-trade-analyzer, economic-calendar-fetcher,
edge-candidate-agent, edge-concept-synthesizer, edge-hint-extractor,
edge-signal-aggregator, edge-strategy-designer, exposure-coach,
finviz-screener, ibd-distribution-day-monitor, kanchi-dividend-review-monitor,
kanchi-dividend-sop, kanchi-dividend-us-tax-accounting,
market-environment-analysis, options-strategy-advisor, pair-trade-screener,
pead-screener, signal-postmortem, skill-integration-tester,
strategy-pivot-designer, trade-hypothesis-ideator, trade-performance-coach,
trader-memory-core, value-dividend-screener

**Proposal:** replace the ~20 hand-written CI steps with a single
`python -m pytest` invocation. `--import-mode=importlib` plus the root
`conftest.py` already make bulk execution safe (verified locally: one
invocation, 3,408 pass). New skills then get CI automatically instead of
requiring a manual ci.yml edit that is evidently not happening.

### 1.2 `testpaths` in pyproject.toml is stale in both directions

- **Ghost entries** (directories that do not exist):
  `skills/relative-strength-momentum-scanner/scripts/tests`,
  `skills/signal-postmortem-analyzer/scripts/tests`,
  `skills/moving-average-regime-detector/scripts/tests`
- **Missing entries** (test files exist but bulk pytest never collects them):
  `signal-postmortem`, `trade-performance-coach`, `value-dividend-screener`,
  `dividend-growth-pullback-screener` (plus the three known-skip skills below).
  The comment `# pair-trade-screener, portfolio-manager, signal-postmortem:
  tests/ exists but no test_*.py` is outdated — signal-postmortem has two
  test files, and all four omitted suites pass when run directly
  (66 passed, 2 skipped, 0.31s).

**Proposal:** delete the ghost entries, add the four omitted suites — or drop
the explicit list entirely in favor of default discovery, which the importlib
mode already supports.

### 1.3 Quarantined suites hide the largest skills

`scripts/run_all_tests.sh` KNOWN_SKIP + CI `continue-on-error`:

| Skill | Why skipped | LOC unmeasured |
|---|---|---|
| theme-detector | "27 pre-existing failures" | 5,016 |
| canslim-screener | needs `bs4` (not in dev extras) | 4,391 of 5,009 |
| pair-trade-screener | needs `statsmodels` (not in dev extras) | 1,073 |

theme-detector is the single largest skill in the repo (5,016 src LOC,
5,862 test LOC) and its entire suite is quarantined. canslim-screener's 13
modules (scorer, 7 calculators, fmp_client, report_generator) run at 0%.

**Proposal:** add `beautifulsoup4` and `statsmodels` to the `dev` extra (or
guard the imports with `pytest.importorskip`, which pair-trade's test already
does — so only the dependency install is missing), and burn down the
theme-detector failures. These three items alone would bring ~10,500 LOC back
under measurement.

### 1.4 `examples/daily-market-dashboard` tests run nowhere

Three test files (`test_app_helpers.py`, `test_generate_dashboard.py`,
`test_sanitizer.py`) are outside both `testpaths` and `run_all_tests.sh`
globs and have no CI step.

---

## 2. Skills with no tests at all

| Skill | Script | LOC | Notes |
|---|---|---|---|
| us-market-bubble-detector | `bubble_scorer.py` | 299 | Pure-calculation scoring (0–16 bubble score). No I/O, trivially testable — cheapest win in the repo. |
| portfolio-manager | `check_alpaca_connection.py` | 278 | `tests/` dir with a conftest exists but zero test files. Network-bound; test with a mocked Alpaca client. |

(market-news-analyst, scenario-analyzer, technical-analyst, us-stock-analysis
have no scripts — knowledge-only skills, nothing to unit-test.)

---

## 3. Untested monoliths inside "tested" skills

These skills nominally have tests, but the tests cover a thin slice
(typically only the FMP `/stable` migration) while the core screening logic
is unmeasured:

| Skill | Untested core | LOC | Existing tests cover |
|---|---|---|---|
| value-dividend-screener | `screen_dividend_stocks.py` | 1,443 | FMP stable endpoint only (13 tests, 218 LOC) |
| dividend-growth-pullback-screener | `screen_dividend_growth.py` | 1,396 | RSI calc + FMP stable only (19 tests) |
| pair-trade-screener | `analyze_spread.py` (465 LOC, **zero** tests) + most of `find_pairs.py` | ~1,000 | one endpoint-fallback function (82-LOC test) |
| trade-performance-coach | `review_trade_performance.py` | 798 | 9 tests, 173 LOC |
| ibd-distribution-day-monitor | `ibd_monitor.py` (main pipeline) | 446 | calculators are tested; the orchestrator is never imported |
| market-breadth-analyzer | `market_breadth_analyzer.py` + `csv_client.py` | 554 | 9 calculator suites, but the CLI/orchestrator and CSV fetch layer never run |
| breadth-chart-analyst | `detect_breadth_values.py`, `extract_chart_right_edge.py` | 869 | other two scripts only |
| trade-hypothesis-ideator | `run_hypothesis_ideator.py` (CLI entry) | 213 | six well-tested submodules |

`analyze_spread.py` deserves emphasis: it implements the cointegration /
z-score math that generates actual trade signals, with no tests at all.

---

## 4. Worst-covered measured files (≥80 stmts, <55%)

| Cov | Stmts | File |
|---:|---:|---|
| 2.1% | 242 | `skills/ftd-detector/scripts/report_generator.py` |
| 17.2% | 163 | `skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py` |
| 21.7% | 360 | `skills/breadth-chart-analyst/scripts/detect_uptrend_ratio.py` |
| 26.9% | 766 | `skills/edge-candidate-agent/scripts/auto_detect_candidates.py` |
| 27.2% | 272 | `skills/parabolic-short-trade-planner/scripts/fmp_client.py` |
| 32.1% | 209 | `skills/earnings-calendar/scripts/fetch_earnings_fmp.py` |
| 36.9% | 236 | `skills/skill-idea-miner/scripts/score_ideas.py` |
| 37.2% | 293 | `skills/pead-screener/scripts/screen_pead.py` |
| 43.5% | 230 | `skills/downtrend-duration-analyzer/scripts/analyze_downtrends.py` |
| 47.6% | 145 | `skills/edge-strategy-designer/scripts/design_strategy_drafts.py` |
| 48.7% | 388 | `skills/vcp-screener/scripts/screen_vcp.py` |
| 49.2% | 246 | `scripts/weekly_core_collect.py` |
| 49.5% | 111 | `scripts/package_skills.py` |
| 53.4% | 204 | `skills/ibd-distribution-day-monitor/scripts/fmp_client.py` |
| 54.5% | 299 | `skills/strategy-pivot-designer/scripts/generate_pivots.py` |

Per-skill aggregates below 50%: canslim-screener 38%, edge-candidate-agent
40%, breadth-chart-analyst 41%, earnings-calendar 44%, downtrend-duration-
analyzer 46%, skill-designer 48%, edge-strategy-designer 48%.

---

## 5. Cross-cutting patterns

1. **Calculators are tested; entry points are not.** The recurring shape is a
   well-tested `calculators/` package under an untested `main()` /
   orchestration script (ibd-monitor, market-breadth, earnings-trade,
   pead, vcp). The parabolic-short-trade-planner shows the fix that already
   works in this repo: fixture-driven smoke tests
   (`test_screen_parabolic_smoke.py`, `--dry-run --fixture`) that exercise
   the whole pipeline offline. Replicating that pattern on the other
   screeners is high leverage per test written.
2. **`fmp_client.py` copies are the highest-churn files in the repo**
   (10 changes in vcp's copy this year) and the shared behavior tests in
   `scripts/tests/test_fmp_client_shared_behavior.py` are the right idea —
   but per-skill copies still measure 27–54% in parabolic, ibd, canslim.
   Since the client is generated (`generate_fmp_client.py` + drift check),
   extending the shared contract tests once covers all copies.
3. **`report_generator.py` modules are chronically untested** (ftd-detector
   2.1%). Golden-file tests against a fixed input dict are cheap and catch
   the format regressions these files keep being edited for.
4. **The coverage gate is decorative.** `fail_under = 40` exists in
   pyproject, but CI never runs a bulk coverage report over everything (the
   per-skill `--cov-append` chain covers only the 20 enumerated skills), so
   the gate binds nothing. Once CI runs a single bulk invocation (§1.1), the
   real number is ~86% of measured code — set the gate near the true floor
   and ratchet it.

---

## 6. Ranked recommendations

1. **CI: one bulk pytest run** replacing hand-enumerated steps (§1.1). Zero
   new tests, ~30 skills' existing suites start gating merges.
2. **Fix `testpaths`** (remove 3 ghosts, add 4 omitted suites) (§1.2).
3. **Add `beautifulsoup4` + `statsmodels` to dev extras** so canslim and
   pair-trade suites run; schedule the theme-detector failure burn-down
   (§1.3) — together ~10.5k LOC back under measurement.
4. **Test the signal-generating monoliths**: `analyze_spread.py` (zero
   tests, cointegration math), `screen_dividend_stocks.py`,
   `screen_dividend_growth.py` core filters (§3). Fixture-driven smoke
   tests + unit tests on the scoring/filter functions.
5. **Cover the two untested skills**: `bubble_scorer.py` (pure calc, easy)
   and `check_alpaca_connection.py` (mocked client) (§2).
6. **Adopt the fixture-smoke-test pattern** for the untested `main()`
   orchestrators (ibd_monitor, market_breadth_analyzer, run_hypothesis_
   ideator, analyze_earnings_trades) (§5.1).
7. **Golden-file tests for report generators**, starting with ftd-detector's
   (2.1%) (§5.3).
8. **Wire `examples/daily-market-dashboard` tests into CI** (§1.4).
9. **Re-arm the coverage gate** after items 1–3 land: measure the true bulk
   number, set `fail_under` just below it, ratchet upward (§5.4).
