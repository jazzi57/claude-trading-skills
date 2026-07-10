---
layout: default
title: "Discord Whatsapp Bridge"
grand_parent: English
parent: Skill Guides
nav_order: 15
lang_peer: /ja/skills/discord-whatsapp-bridge/
permalink: /en/skills/discord-whatsapp-bridge/
generated: true
---

# Discord Whatsapp Bridge
{: .no_toc }

Set up and operate a Discord-to-WhatsApp bridge that forwards trading alerts from Discord channels to a WhatsApp number. Use when configuring alert delivery from Discord signal channels, screener webhook channels, or intraday monitor notifications to a phone via WhatsApp, including channel mapping, keyword filtering, config validation, and unattended deployment.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/discord-whatsapp-bridge){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

Configure, validate, and operate a long-running Node.js bridge that watches
selected Discord channels and forwards matching messages to a WhatsApp number
in real time. Channel mappings and keyword filters live in a JSON config; a
Python validator checks the config and environment before the bridge starts.
Adapted for trading workflows: forward screener hits, entry/stop alerts, and
intraday trigger notifications to the phone while keeping analysis in the
originating skills.

---

## 2. When to Use

- Delivering trading alerts from Discord signal channels to WhatsApp
- Relaying screener output (vcp-screener, earnings-trade-analyzer) posted to a
  private Discord channel via webhook onward to a phone
- Forwarding intraday state transitions (e.g. parabolic-short Phase 3
  armed → triggered) with keyword filters
- Diagnosing a bridge that stopped forwarding (config, intents, pairing)

---

## 3. Prerequisites

- Node.js v18+ for the bridge runtime
- Python 3.9+ for the config validator (standard library only)
- A Discord bot token with the **Message Content** privileged intent enabled
- A WhatsApp account able to scan a QR code for device linking
- No paid API subscriptions required

---

## 4. Quick Start

```bash
# Validate the channel-mapping config and environment before starting
python3 skills/discord-whatsapp-bridge/scripts/validate_bridge_config.py \
  --config skills/discord-whatsapp-bridge/assets/bridge_config.example.json \
  --check-env --output-dir reports/

# Install and start the Node.js bridge (first run shows a WhatsApp QR code)
cd skills/discord-whatsapp-bridge/scripts/bridge
npm install
npm start
```

---

## 5. Workflow

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

---

## 6. Resources

**References:**

- `skills/discord-whatsapp-bridge/references/alert_forwarding_patterns.md`
- `skills/discord-whatsapp-bridge/references/setup_guide.md`

**Scripts:**

- `skills/discord-whatsapp-bridge/scripts/validate_bridge_config.py`
