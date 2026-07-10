---
name: discord-whatsapp-bridge
description: Set up and operate a Discord-to-WhatsApp bridge that forwards trading alerts from Discord channels to a WhatsApp number. Use when configuring alert delivery from Discord signal channels, screener webhook channels, or intraday monitor notifications to a phone via WhatsApp, including channel mapping, keyword filtering, config validation, and unattended deployment.
---

## Overview

Configure, validate, and operate a long-running Node.js bridge that watches
selected Discord channels and forwards matching messages to a WhatsApp number
in real time. Channel mappings and keyword filters live in a JSON config; a
Python validator checks the config and environment before the bridge starts.
Adapted for trading workflows: forward screener hits, entry/stop alerts, and
intraday trigger notifications to the phone while keeping analysis in the
originating skills.

## When to Use

- Delivering trading alerts from Discord signal channels to WhatsApp
- Relaying screener output (vcp-screener, earnings-trade-analyzer) posted to a
  private Discord channel via webhook onward to a phone
- Forwarding intraday state transitions (e.g. parabolic-short Phase 3
  armed → triggered) with keyword filters
- Diagnosing a bridge that stopped forwarding (config, intents, pairing)

## Prerequisites

- Node.js v18+ for the bridge runtime
- Python 3.9+ for the config validator (standard library only)
- A Discord bot token with the **Message Content** privileged intent enabled
- A WhatsApp account able to scan a QR code for device linking
- No paid API subscriptions required

## Workflow

### Step 1: Gather Requirements

Ask which Discord channels should be forwarded, what filters apply, and the
destination number. For channel selection guidance, read
`references/alert_forwarding_patterns.md` (forward triggers, not commentary;
prefer keyword filters over unfiltered channels).

### Step 2: Build the Config

Copy `assets/bridge_config.example.json` and edit one entry per channel:

```json
{
  "channels": [
    {
      "label": "VCP Breakout Alerts",
      "guild_id": "132182129704239114",
      "channel_id": "132182129704239145",
      "keywords": ["breakout", "entry", "stop"],
      "enabled": true
    }
  ],
  "forwarding": {
    "include_author": true,
    "include_attachments": true,
    "rate_limit_per_minute": 20
  }
}
```

Guild and channel IDs are Discord snowflakes and must be JSON **strings**.
Copy them via Discord Developer Mode (right-click → Copy ID). Secrets go in a
`.env` file (never committed): copy `assets/env.example` to
`scripts/bridge/.env` and set `DISCORD_BOT_TOKEN` and
`WHATSAPP_TARGET_NUMBER` (digits only, country code + number, no `+`).

### Step 3: Validate the Config

Run the validator before starting the bridge:

```bash
python3 skills/discord-whatsapp-bridge/scripts/validate_bridge_config.py \
  --config /path/to/bridge_config.json \
  --check-env \
  --output-dir reports/
```

Resolve every ERROR (bridge will not work) and review WARNINGs (duplicate
channels, disabled channels, unusual ID lengths). The validator writes a
markdown + JSON report to `reports/`.

### Step 4: Install and Start the Bridge

```bash
cd skills/discord-whatsapp-bridge/scripts/bridge
npm install
npm start
```

On first run, scan the QR code with WhatsApp (Settings → Linked Devices).
Follow `references/setup_guide.md` for Discord bot creation, intent setup,
and pairing details. Confirm the startup checklist: Discord login line, one
`Watching #channel` line per mapping, `WhatsApp client is ready.`, and the
`🔄 Trading-alert bridge connected.` message on the phone.

### Step 5: Deploy Unattended

For continuous forwarding, run the bridge under a process supervisor
(launchd on macOS, systemd on Linux, or pm2), per the "Running Unattended"
section of `references/setup_guide.md`. The WhatsApp session persists in
`.wwebjs_auth/`, so restarts do not require re-pairing.

### Step 6: Verify and Tune

Post a test message in a watched channel and confirm WhatsApp delivery with
the expected format (label header, author, body, attachment URLs). If volume
is too high, tighten `keywords` per the filter recipes in
`references/alert_forwarding_patterns.md` rather than raising the rate limit.

## Output Format

Forwarded WhatsApp messages follow this template:

```
📈 *VCP Breakout Alerts*
👤 screener-bot
━━━━━━━━━━
NVDA breakout entry 142.50, stop 138.20
📎 https://cdn.discordapp.com/attachments/.../chart.png
━━━━━━━━━━
```

Validator reports are written to `reports/`:

- `discord_whatsapp_bridge_check_<date>_<time>.md` — findings grouped by
  severity (ERROR / WARNING / INFO) with an overall VALID/INVALID result
- `discord_whatsapp_bridge_check_<date>_<time>.json` — machine-readable
  findings with `valid` flag

## Resources

- `scripts/validate_bridge_config.py` — config + environment validator
- `scripts/bridge/index.js` — the Node.js bridge (discord.js + whatsapp-web.js)
- `scripts/bridge/package.json` — bridge dependencies and start scripts
- `assets/bridge_config.example.json` — channel-mapping config template
- `assets/env.example` — environment variable template
- `references/setup_guide.md` — bot creation, pairing, deployment, troubleshooting
- `references/alert_forwarding_patterns.md` — channel selection and filter recipes

## Key Principles

1. **Validate before running.** Every config change goes through
   `validate_bridge_config.py` first; snowflake-as-number and duplicate
   channel mistakes are silent failures at runtime but explicit findings in
   the validator.

2. **Delivery only, no analysis.** The bridge moves final, human-readable
   summaries to the phone. Position sizing, entries, and record-keeping stay
   in position-sizer, technical-analyst, and trader-memory-core.

3. **Conservative volume.** whatsapp-web.js automates WhatsApp Web
   unofficially; high automated volume risks account restriction. Keep the
   default rate limit (20/minute), filter aggressively, and forward to the
   trader's own number only.

4. **Secrets never enter the repository.** `.env`, `.wwebjs_auth/` session
   caches, and personal config JSONs stay local. Only the sanitized example
   templates in `assets/` are committed.
