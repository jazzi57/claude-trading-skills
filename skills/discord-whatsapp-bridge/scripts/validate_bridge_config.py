#!/usr/bin/env python3
"""Validate a Discord-WhatsApp bridge configuration file.

Checks the JSON channel-mapping config consumed by the Node.js bridge
(``scripts/bridge/index.js``) before the bridge is started: channel
mapping structure, Discord snowflake ID formats, keyword filters,
forwarding options, and (optionally) required environment variables.

Advisory categories:
- ERROR   -- the bridge will not work; must be fixed
- WARNING -- likely misconfiguration; human review recommended
- INFO    -- informational note

Exit codes: 0 = config valid (no ERROR findings), 1 = errors found or
the script itself failed (missing file, malformed JSON).

Usage:
    python3 validate_bridge_config.py --config assets/bridge_config.example.json
    python3 validate_bridge_config.py --config my_config.json --check-env
"""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

REQUIRED_ENV_VARS = ("DISCORD_BOT_TOKEN", "WHATSAPP_TARGET_NUMBER")

KNOWN_TOP_LEVEL_KEYS = {"channels", "forwarding"}
KNOWN_CHANNEL_KEYS = {"label", "guild_id", "channel_id", "keywords", "enabled"}
KNOWN_FORWARDING_KEYS = {
    "include_author",
    "include_attachments",
    "rate_limit_per_minute",
}
FORWARDING_BOOL_KEYS = ("include_author", "include_attachments")

# Discord snowflakes are 64-bit ints, in practice 17-20 decimal digits.
SNOWFLAKE_MIN_DIGITS = 17
SNOWFLAKE_MAX_DIGITS = 20

# Shortest assigned E.164 numbers (country code + subscriber) are 7 digits.
MIN_PHONE_DIGITS = 7
MAX_PHONE_DIGITS = 15


@dataclass(frozen=True)
class Finding:
    severity: str  # ERROR | WARNING | INFO
    category: str
    message: str


def _error(category: str, message: str) -> Finding:
    return Finding("ERROR", category, message)


def _warning(category: str, message: str) -> Finding:
    return Finding("WARNING", category, message)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _validate_snowflake(value: object, field: str, where: str) -> list:
    findings = []
    if isinstance(value, int):
        # Snowflakes exceed 2^53, so JSON numbers silently lose precision
        # in JavaScript. The Node bridge requires them as strings.
        findings.append(
            _error(
                "channels",
                f"{where}: {field} must be a JSON string, not a number "
                "(Discord IDs lose precision as JavaScript numbers)",
            )
        )
        return findings
    if not isinstance(value, str) or not value:
        findings.append(_error("channels", f"{where}: missing or invalid {field}"))
        return findings
    if not value.isdigit():
        findings.append(_error("channels", f"{where}: {field} {value!r} must contain only digits"))
        return findings
    if not (SNOWFLAKE_MIN_DIGITS <= len(value) <= SNOWFLAKE_MAX_DIGITS):
        findings.append(
            _warning(
                "channels",
                f"{where}: {field} {value!r} has {len(value)} digits; Discord IDs "
                f"are normally {SNOWFLAKE_MIN_DIGITS}-{SNOWFLAKE_MAX_DIGITS} digits",
            )
        )
    return findings


def validate_channel(channel: object, index: int) -> list:
    """Validate a single channel mapping entry."""
    where = f"channels[{index}]"
    if not isinstance(channel, dict):
        return [_error("channels", f"{where}: entry must be an object")]

    findings = []

    label = channel.get("label")
    if not isinstance(label, str) or not label.strip():
        findings.append(_error("channels", f"{where}: missing or empty label"))

    for field in ("guild_id", "channel_id"):
        findings.extend(_validate_snowflake(channel.get(field), field, where))

    if "keywords" in channel:
        keywords = channel["keywords"]
        if not isinstance(keywords, list):
            findings.append(_error("channels", f"{where}: keywords must be a list of strings"))
        else:
            for i, keyword in enumerate(keywords):
                if not isinstance(keyword, str) or not keyword.strip():
                    findings.append(
                        _error(
                            "channels",
                            f"{where}: keywords[{i}] must be a non-empty string",
                        )
                    )

    if "enabled" in channel and not isinstance(channel["enabled"], bool):
        findings.append(_error("channels", f"{where}: enabled must be true or false"))

    for key in channel:
        if key not in KNOWN_CHANNEL_KEYS:
            findings.append(_warning("channels", f"{where}: unknown key {key!r} will be ignored"))

    return findings


def _validate_forwarding(forwarding: object) -> list:
    if not isinstance(forwarding, dict):
        return [_error("forwarding", "forwarding must be an object")]

    findings = []
    for key in FORWARDING_BOOL_KEYS:
        if key in forwarding and not isinstance(forwarding[key], bool):
            findings.append(_error("forwarding", f"forwarding.{key} must be true or false"))

    if "rate_limit_per_minute" in forwarding:
        rate = forwarding["rate_limit_per_minute"]
        if not isinstance(rate, int) or isinstance(rate, bool) or rate < 1:
            findings.append(
                _error(
                    "forwarding",
                    "forwarding.rate_limit_per_minute must be a positive integer",
                )
            )

    for key in forwarding:
        if key not in KNOWN_FORWARDING_KEYS:
            findings.append(
                _warning("forwarding", f"forwarding: unknown key {key!r} will be ignored")
            )

    return findings


def validate_config(config: object) -> list:
    """Validate the full bridge config object. Returns a list of Findings."""
    if not isinstance(config, dict):
        return [_error("structure", "config root must be a JSON object")]

    findings = []

    channels = config.get("channels")
    if channels is None:
        findings.append(_error("structure", "missing required key: channels"))
    elif not isinstance(channels, list):
        findings.append(_error("structure", "channels must be a list"))
    elif not channels:
        findings.append(_error("structure", "channels must contain at least one entry"))
    else:
        seen_channel_ids = set()
        any_enabled = False
        for i, channel in enumerate(channels):
            findings.extend(validate_channel(channel, i))
            if isinstance(channel, dict):
                channel_id = channel.get("channel_id")
                if isinstance(channel_id, str):
                    if channel_id in seen_channel_ids:
                        findings.append(
                            _warning(
                                "channels",
                                f"channels[{i}]: duplicate channel_id {channel_id!r} "
                                "(messages would forward twice)",
                            )
                        )
                    seen_channel_ids.add(channel_id)
                if channel.get("enabled", True) is True:
                    any_enabled = True
        if not any_enabled:
            findings.append(_warning("channels", "all channels are disabled; nothing will forward"))

    if "forwarding" in config:
        findings.extend(_validate_forwarding(config["forwarding"]))

    for key in config:
        if key not in KNOWN_TOP_LEVEL_KEYS:
            findings.append(_warning("structure", f"unknown top-level key {key!r} will be ignored"))

    return findings


def validate_target_number(number: str) -> list:
    """Validate a WhatsApp target number (digits only, E.164 without '+')."""
    if not isinstance(number, str) or not number:
        return [_error("whatsapp", "target number is empty")]
    if number.startswith("+"):
        return [
            _error(
                "whatsapp",
                f"target number {number!r} must not include '+'; use digits only "
                "(country code + number, e.g. 15551234567)",
            )
        ]
    if not number.isdigit():
        return [
            _error(
                "whatsapp",
                f"target number {number!r} must contain only digits "
                "(no spaces, dashes, or parentheses)",
            )
        ]
    if not (MIN_PHONE_DIGITS <= len(number) <= MAX_PHONE_DIGITS):
        return [
            _warning(
                "whatsapp",
                f"target number has {len(number)} digits; expected "
                f"{MIN_PHONE_DIGITS}-{MAX_PHONE_DIGITS} (country code + number)",
            )
        ]
    return []


def format_whatsapp_chat_id(number: str) -> str:
    """Return the whatsapp-web.js chat ID for a digits-only number."""
    return f"{number}@c.us"


def check_env(env=None) -> list:
    """Check that required environment variables are present and sane."""
    if env is None:
        env = os.environ
    findings = []
    for var in REQUIRED_ENV_VARS:
        if not env.get(var):
            findings.append(_error("env", f"{var} is not set (add it to .env or export it)"))
    target = env.get("WHATSAPP_TARGET_NUMBER")
    if target:
        findings.extend(validate_target_number(target))
    return findings


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def build_markdown_report(config_path: str, findings: list, timestamp: str) -> str:
    valid = not any(f.severity == "ERROR" for f in findings)
    lines = [
        "# Discord-WhatsApp Bridge Config Check",
        f"**Config:** {config_path}",
        f"**Generated:** {timestamp}",
        f"**Result:** {'VALID' if valid else 'INVALID'}",
        f"**Total findings:** {len(findings)}",
        "",
    ]
    for severity in ("ERROR", "WARNING", "INFO"):
        group = [f for f in findings if f.severity == severity]
        if not group:
            continue
        lines.append(f"## {severity} ({len(group)})")
        for f in group:
            lines.append(f"- **[{f.category}]** {f.message}")
        lines.append("")
    if not findings:
        lines.append("No issues found. The bridge config is ready to use.")
        lines.append("")
    return "\n".join(lines)


def write_reports(output_dir: Path, config_path: str, findings: list) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    valid = not any(f.severity == "ERROR" for f in findings)

    md_path = output_dir / f"discord_whatsapp_bridge_check_{stamp}.md"
    md_path.write_text(build_markdown_report(config_path, findings, timestamp))

    json_path = output_dir / f"discord_whatsapp_bridge_check_{stamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "config": config_path,
                "generated": timestamp,
                "valid": valid,
                "findings": [asdict(f) for f in findings],
            },
            indent=2,
        )
    )
    print(f"Reports written: {md_path} / {json_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Discord-WhatsApp bridge config file")
    parser.add_argument("--config", required=True, help="Path to bridge_config.json")
    parser.add_argument(
        "--check-env",
        action="store_true",
        help="Also verify DISCORD_BOT_TOKEN / WHATSAPP_TARGET_NUMBER env vars",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/",
        help="Directory for validation reports (default: reports/)",
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        config = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"Error: malformed JSON in {config_path}: {exc}", file=sys.stderr)
        return 1

    findings = validate_config(config)
    if args.check_env:
        findings.extend(check_env())

    for f in findings:
        stream = sys.stderr if f.severity == "ERROR" else sys.stdout
        print(f"[{f.severity}] [{f.category}] {f.message}", file=stream)

    write_reports(Path(args.output_dir), str(config_path), findings)

    if any(f.severity == "ERROR" for f in findings):
        return 1
    print("Config is valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
