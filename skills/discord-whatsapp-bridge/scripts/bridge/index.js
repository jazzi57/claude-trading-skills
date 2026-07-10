/**
 * Discord -> WhatsApp trading-alert bridge.
 *
 * Watches the Discord channels listed in bridge_config.json and forwards
 * matching messages to a WhatsApp number via whatsapp-web.js.
 *
 * Environment variables (via .env or the shell):
 *   DISCORD_BOT_TOKEN       Discord bot token (Message Content intent enabled)
 *   WHATSAPP_TARGET_NUMBER  Digits-only destination number, e.g. 15551234567
 *   BRIDGE_CONFIG_PATH      Optional path to the config JSON
 *                           (default: ../../assets/bridge_config.example.json)
 *
 * Validate the config first:
 *   python3 ../validate_bridge_config.py --config <config> --check-env
 */

require('dotenv').config();

const path = require('path');
const { Client: DiscordClient, GatewayIntentBits } = require('discord.js');
const { Client: WhatsAppClient, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');

const config = loadConfig();
const targetChatId = `${requireEnv('WHATSAPP_TARGET_NUMBER')}@c.us`;

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    console.error(`Missing required environment variable: ${name}`);
    process.exit(1);
  }
  return value;
}

function loadConfig() {
  const configPath =
    process.env.BRIDGE_CONFIG_PATH ||
    path.join(__dirname, '..', '..', 'assets', 'bridge_config.example.json');
  // eslint-disable-next-line import/no-dynamic-require, global-require
  const raw = require(path.resolve(configPath));
  const channels = (raw.channels || []).filter((c) => c.enabled !== false);
  if (channels.length === 0) {
    console.error(`No enabled channels in ${configPath}; nothing to forward.`);
    process.exit(1);
  }
  return {
    channels,
    forwarding: {
      include_author: true,
      include_attachments: true,
      rate_limit_per_minute: 20,
      ...(raw.forwarding || {}),
    },
  };
}

// --- Rate limiter (sliding one-minute window) ------------------------------

const sentTimestamps = [];

function underRateLimit() {
  const cutoff = Date.now() - 60_000;
  while (sentTimestamps.length > 0 && sentTimestamps[0] < cutoff) {
    sentTimestamps.shift();
  }
  return sentTimestamps.length < config.forwarding.rate_limit_per_minute;
}

// --- Message matching and formatting ---------------------------------------

function matchChannel(message) {
  return config.channels.find(
    (c) =>
      message.guild &&
      message.guild.id === c.guild_id &&
      message.channel.id === c.channel_id,
  );
}

function passesKeywordFilter(channel, content) {
  if (!channel.keywords || channel.keywords.length === 0) return true;
  const haystack = content.toLowerCase();
  return channel.keywords.some((k) => haystack.includes(k.toLowerCase()));
}

function formatForWhatsApp(message, channel) {
  const lines = [`📈 *${channel.label}*`];
  if (config.forwarding.include_author) {
    lines.push(`👤 ${message.author.username}`);
  }
  lines.push('━━━━━━━━━━');
  if (message.content) {
    lines.push(message.content);
  }
  if (config.forwarding.include_attachments && message.attachments.size > 0) {
    for (const attachment of message.attachments.values()) {
      lines.push(`📎 ${attachment.url}`);
    }
  }
  lines.push('━━━━━━━━━━');
  return lines.join('\n');
}

// --- Clients ----------------------------------------------------------------

let whatsappReady = false;

const discordClient = new DiscordClient({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
});

const whatsappClient = new WhatsAppClient({
  authStrategy: new LocalAuth(),
  puppeteer: {
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--no-first-run',
    ],
  },
});

whatsappClient.on('qr', (qr) => {
  qrcode.generate(qr, { small: true });
  console.log('Scan the QR code above with WhatsApp (Linked Devices).');
});

whatsappClient.on('ready', async () => {
  whatsappReady = true;
  console.log('WhatsApp client is ready.');
  try {
    await whatsappClient.sendMessage(targetChatId, '🔄 Trading-alert bridge connected.');
  } catch (error) {
    console.error('Failed to send WhatsApp test message:', error.message);
  }
});

whatsappClient.on('disconnected', (reason) => {
  whatsappReady = false;
  console.error('WhatsApp disconnected:', reason);
});

whatsappClient.on('auth_failure', (message) => {
  console.error('WhatsApp authentication failed:', message);
});

discordClient.on('ready', async () => {
  console.log(`Discord logged in as ${discordClient.user.tag}`);
  for (const channel of config.channels) {
    try {
      const resolved = await discordClient.channels.fetch(channel.channel_id);
      console.log(`Watching #${resolved.name} (${channel.label})`);
    } catch (error) {
      console.error(
        `Cannot access channel ${channel.channel_id} (${channel.label}): ${error.message}`,
      );
    }
  }
});

discordClient.on('messageCreate', async (message) => {
  // Trading-signal channels usually post via bots/webhooks, so bot messages
  // are forwarded; only this bridge's own messages are skipped.
  if (message.author.id === discordClient.user.id) return;

  const channel = matchChannel(message);
  if (!channel) return;
  if (!passesKeywordFilter(channel, message.content || '')) return;

  if (!whatsappReady) {
    console.warn(`WhatsApp not ready; dropping message from ${channel.label}.`);
    return;
  }
  if (!underRateLimit()) {
    console.warn(`Rate limit reached; dropping message from ${channel.label}.`);
    return;
  }

  try {
    await whatsappClient.sendMessage(targetChatId, formatForWhatsApp(message, channel));
    sentTimestamps.push(Date.now());
    console.log(`Forwarded message from ${channel.label}.`);
  } catch (error) {
    console.error(`Failed to forward from ${channel.label}:`, error.message);
  }
});

process.on('unhandledRejection', (error) => {
  console.error('Unhandled promise rejection:', error);
});

process.on('SIGINT', async () => {
  console.log('Shutting down bridge...');
  await Promise.allSettled([whatsappClient.destroy(), discordClient.destroy()]);
  process.exit(0);
});

discordClient.login(requireEnv('DISCORD_BOT_TOKEN'));
whatsappClient.initialize();
