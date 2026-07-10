# Discord-WhatsApp Bridge Setup Guide

Step-by-step setup for the Node.js bridge in `scripts/bridge/`. The bridge is
a long-running process: it stays connected to both Discord (as a bot) and
WhatsApp (as a linked device) and forwards matching messages in real time.

## 1. Prerequisites

- Node.js v18 or higher (`node --version`)
- A Discord account with permission to add a bot to the target server, or
  membership in a server whose alerts should be forwarded
- A WhatsApp account on a phone that can scan a QR code
- Python 3.9+ for the config validator (standard library only)

## 2. Create the Discord Bot

1. Open https://discord.com/developers/applications and click **New Application**.
2. Name it (e.g. `trading-alert-bridge`) and create it.
3. In **Bot** settings:
   - Click **Reset Token** and copy the token — this becomes `DISCORD_BOT_TOKEN`.
   - Under **Privileged Gateway Intents**, enable **Message Content Intent**.
     Without it the bot receives empty message bodies.
4. In **OAuth2 → URL Generator**:
   - Scopes: `bot`
   - Bot permissions: `View Channels`, `Read Message History`
   - Open the generated URL and invite the bot to the server.

If the alerts come from a server that is not yours, ask an admin to invite the
bot, or run the bridge against a server you control that mirrors the alerts.

## 3. Collect Guild and Channel IDs

1. In Discord, open **User Settings → Advanced** and enable **Developer Mode**.
2. Right-click the server icon → **Copy Server ID** — this is `guild_id`.
3. Right-click the target channel → **Copy Channel ID** — this is `channel_id`.

Discord IDs (snowflakes) are 17-20 digit numbers. In `bridge_config.json` they
must be written as **strings** (`"132182129704239114"`), never bare numbers —
JavaScript loses precision on integers that large.

## 4. Configure the Bridge

1. Copy `assets/bridge_config.example.json` to a working location and edit:
   - One entry per Discord channel to watch
   - `label`: name shown in the WhatsApp message header
   - `keywords`: optional case-insensitive filter; empty list forwards everything
   - `enabled`: set `false` to pause a channel without deleting it
2. Copy `assets/env.example` to `scripts/bridge/.env` and fill in:
   - `DISCORD_BOT_TOKEN`
   - `WHATSAPP_TARGET_NUMBER` (digits only, country code + number, no `+`)
   - `BRIDGE_CONFIG_PATH` if the config is not the bundled example
3. Validate before starting:

```bash
python3 skills/discord-whatsapp-bridge/scripts/validate_bridge_config.py \
  --config /path/to/bridge_config.json --check-env
```

## 5. First Run and WhatsApp Pairing

```bash
cd skills/discord-whatsapp-bridge/scripts/bridge
npm install
npm start
```

On first start the bridge prints a QR code in the terminal. On the phone:
**WhatsApp → Settings → Linked Devices → Link a Device**, then scan the code.

The session is cached in `.wwebjs_auth/` (LocalAuth), so subsequent starts do
not require re-scanning unless the device is unlinked or the cache is deleted.

Successful startup looks like:

```
Discord logged in as trading-alert-bridge#1234
Watching #vcp-alerts (VCP Breakout Alerts)
WhatsApp client is ready.
```

and a `🔄 Trading-alert bridge connected.` message arrives on WhatsApp.

## 6. Running Unattended

The bridge must stay running to forward messages. Options:

- **macOS (launchd)**: create a LaunchAgent that runs `node index.js` with
  `KeepAlive: true`, mirroring the plists in this repository's `launchd/`
  directory.
- **Linux (systemd)**: a user service with `Restart=always`.
- **Any platform**: `pm2 start index.js --name discord-whatsapp-bridge`.

Run it on a machine that stays awake; puppeteer keeps a headless Chromium
open for the WhatsApp Web session (~300-500 MB RAM).

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Message bodies are empty | Message Content intent disabled | Enable it in the developer portal (Bot settings) |
| `Cannot access channel ...` at startup | Bot not invited or lacks View Channels | Re-invite with correct permissions |
| QR code loops forever | Stale auth cache | Delete `.wwebjs_auth/` and re-pair |
| `WhatsApp disconnected: NAVIGATION` | WhatsApp Web session invalidated | Restart the bridge and re-scan the QR code |
| Nothing forwards but startup is clean | Keyword filter too strict, or channel `enabled: false` | Check `keywords` and `enabled` in the config |
| Messages forward twice | Same `channel_id` listed twice | Run the validator; it warns on duplicates |
| Chromium fails to launch on a server | Missing sandbox deps | The bundled launch flags already pass `--no-sandbox`; install Chromium system deps if it still fails |

## 8. Important Caveats

- **whatsapp-web.js is an unofficial library.** It automates WhatsApp Web and
  is not endorsed by WhatsApp. Accounts that send high volumes of automated
  messages risk being restricted or banned. Keep the rate limit conservative
  (default 20/minute) and forward to your own number only.
- **Secrets stay local.** `.env`, `.wwebjs_auth/`, and any personal config
  JSON must never be committed to this public repository.
- **Discord Terms of Service** allow bots, but only in servers where the bot
  was legitimately invited. Do not use a user-account token (self-bot) — that
  violates Discord ToS.
