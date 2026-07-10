# Alert Forwarding Patterns for Trading Workflows

Guidance for deciding *which* Discord channels to bridge to WhatsApp and how
to filter them so the phone receives actionable signals, not noise.

## Selection Principles

1. **Forward triggers, not commentary.** Bridge channels that emit discrete,
   actionable events (entry alerts, stop updates, screener hits). General
   chat and macro-discussion channels create alert fatigue.
2. **One label per decision context.** The `label` field is the first line of
   every WhatsApp message. Name it after the decision it prompts
   ("VCP Breakout Alerts", "Stop-Loss Updates"), not after the Discord
   channel name.
3. **Prefer fewer channels with keyword filters** over many unfiltered
   channels. A missed alert is recoverable at the next review; a numbed-out
   trader who ignores WhatsApp entirely is not.

## Keyword Filter Recipes

Keywords are case-insensitive substrings; a message is forwarded when **any**
keyword matches. An empty `keywords` list forwards everything.

| Goal | Keywords |
|---|---|
| Breakout entries only | `["breakout", "entry", "buy point"]` |
| Risk management events | `["stop", "exit", "trim", "sell"]` |
| Specific tickers | `["NVDA", "MSFT", "AAPL"]` |
| Earnings-related alerts | `["earnings", "gap", "guidance"]` |
| High-urgency only | `["alert", "triggered", "now"]` |

Notes:

- Substring matching means `"buy"` also matches "buyback" — prefer longer,
  specific phrases when a channel is chatty.
- Ticker filters match message text only; alerts posted as images pass the
  filter only if the caption matches (attachments are forwarded as URLs).

## Cadence and Volume

- The default rate limit (20 messages/minute) is a ceiling, not a target.
  A healthy setup forwards a handful of messages per day.
- If a channel regularly hits the rate limit, its filter is too loose —
  tighten keywords rather than raising the limit. High automated volume also
  increases the WhatsApp account-restriction risk.
- For daily-digest style channels (e.g. screener summaries posted once per
  day), no keywords are needed; volume is inherently bounded.

## Integration with Repository Workflows

The bridge is a delivery channel, not an analysis step. Typical pairings:

- **Screener output delivery**: a launchd/cron job runs a screener skill
  (vcp-screener, earnings-trade-analyzer) and posts the summary to a private
  Discord channel via webhook; the bridge relays it to WhatsApp.
- **Intraday trigger notifications**: `parabolic-short-trade-planner`'s
  Phase 3 monitor or other intraday jobs post state transitions
  (armed → triggered) to Discord; the bridge forwards only
  `["triggered", "invalidated"]`.
- **Review reminders**: `trader-memory-core` review-due output posted on a
  schedule, forwarded without filters.

In all cases the analysis happens in the skill; the bridge only moves the
final, human-readable summary to the phone.

## Anti-Patterns

- **Bridging someone else's paid signal service to third parties.** Legal and
  ToS risk; forward to your own number only.
- **Acting on forwarded alerts without the source context.** WhatsApp shows
  the message text only. Position sizing, stops, and portfolio fit still come
  from the planning skills (position-sizer, technical-analyst).
- **Using the bridge as the trade log.** WhatsApp history is not queryable.
  Record trades in trader-memory-core; treat the bridge as ephemeral
  notification transport.
