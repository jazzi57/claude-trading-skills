"""Tests for validate_bridge_config.py (TDD-first)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from validate_bridge_config import (
    check_env,
    format_whatsapp_chat_id,
    validate_channel,
    validate_config,
    validate_target_number,
)

SCRIPT = Path(__file__).resolve().parents[1] / "validate_bridge_config.py"


def valid_config() -> dict:
    """A minimal fully-valid config used as the base for mutations."""
    return {
        "channels": [
            {
                "label": "VCP Alerts",
                "guild_id": "132182129704239114",
                "channel_id": "132182129704239145",
                "keywords": ["breakout", "entry"],
                "enabled": True,
            }
        ],
        "forwarding": {
            "include_author": True,
            "include_attachments": False,
            "rate_limit_per_minute": 20,
        },
    }


def severities(findings) -> set:
    return {f.severity for f in findings}


def messages(findings) -> str:
    return "\n".join(f.message for f in findings)


# ---------------------------------------------------------------------------
# validate_config: happy path
# ---------------------------------------------------------------------------


class TestValidConfig:
    def test_valid_config_has_no_errors(self):
        findings = validate_config(valid_config())
        assert "ERROR" not in severities(findings)

    def test_minimal_channel_without_optional_fields_is_valid(self):
        config = {
            "channels": [
                {
                    "label": "Alerts",
                    "guild_id": "132182129704239114",
                    "channel_id": "132182129704239145",
                }
            ]
        }
        findings = validate_config(config)
        assert "ERROR" not in severities(findings)


# ---------------------------------------------------------------------------
# validate_config: structural errors
# ---------------------------------------------------------------------------


class TestStructuralErrors:
    def test_non_dict_config_is_error(self):
        findings = validate_config(["not", "a", "dict"])
        assert "ERROR" in severities(findings)

    def test_missing_channels_is_error(self):
        findings = validate_config({})
        assert "ERROR" in severities(findings)
        assert "channels" in messages(findings)

    def test_empty_channels_is_error(self):
        findings = validate_config({"channels": []})
        assert "ERROR" in severities(findings)

    def test_channels_not_a_list_is_error(self):
        findings = validate_config({"channels": {"label": "x"}})
        assert "ERROR" in severities(findings)

    def test_unknown_top_level_key_is_warning(self):
        config = valid_config()
        config["channel_list"] = []
        findings = validate_config(config)
        assert any(f.severity == "WARNING" and "channel_list" in f.message for f in findings)


# ---------------------------------------------------------------------------
# validate_channel
# ---------------------------------------------------------------------------


class TestValidateChannel:
    def test_missing_label_is_error(self):
        channel = {"guild_id": "132182129704239114", "channel_id": "132182129704239145"}
        findings = validate_channel(channel, index=0)
        assert "ERROR" in severities(findings)
        assert "label" in messages(findings)

    def test_non_numeric_guild_id_is_error(self):
        channel = {
            "label": "x",
            "guild_id": "my-server",
            "channel_id": "132182129704239145",
        }
        findings = validate_channel(channel, index=0)
        assert "ERROR" in severities(findings)

    def test_snowflake_length_out_of_range_is_warning(self):
        channel = {"label": "x", "guild_id": "12345", "channel_id": "132182129704239145"}
        findings = validate_channel(channel, index=0)
        assert any(f.severity == "WARNING" and "guild_id" in f.message for f in findings)

    def test_integer_ids_are_rejected_with_hint(self):
        # Discord snowflakes exceed 2^53; they must be JSON strings.
        channel = {"label": "x", "guild_id": 132182129704239114, "channel_id": 132182129704239145}
        findings = validate_channel(channel, index=0)
        assert "ERROR" in severities(findings)
        assert "string" in messages(findings)

    def test_keywords_must_be_list_of_strings(self):
        channel = {
            "label": "x",
            "guild_id": "132182129704239114",
            "channel_id": "132182129704239145",
            "keywords": "breakout",
        }
        findings = validate_channel(channel, index=0)
        assert "ERROR" in severities(findings)

    def test_empty_keyword_is_error(self):
        channel = {
            "label": "x",
            "guild_id": "132182129704239114",
            "channel_id": "132182129704239145",
            "keywords": ["breakout", ""],
        }
        findings = validate_channel(channel, index=0)
        assert "ERROR" in severities(findings)

    def test_enabled_must_be_bool(self):
        channel = {
            "label": "x",
            "guild_id": "132182129704239114",
            "channel_id": "132182129704239145",
            "enabled": "yes",
        }
        findings = validate_channel(channel, index=0)
        assert "ERROR" in severities(findings)


class TestDuplicateChannels:
    def test_duplicate_channel_id_is_warning(self):
        config = valid_config()
        dup = dict(config["channels"][0])
        dup["label"] = "Duplicate"
        config["channels"].append(dup)
        findings = validate_config(config)
        assert any(f.severity == "WARNING" and "duplicate" in f.message.lower() for f in findings)

    def test_all_channels_disabled_is_warning(self):
        config = valid_config()
        config["channels"][0]["enabled"] = False
        findings = validate_config(config)
        assert any(f.severity == "WARNING" and "disabled" in f.message.lower() for f in findings)


# ---------------------------------------------------------------------------
# forwarding options
# ---------------------------------------------------------------------------


class TestForwardingOptions:
    def test_rate_limit_zero_is_error(self):
        config = valid_config()
        config["forwarding"]["rate_limit_per_minute"] = 0
        findings = validate_config(config)
        assert "ERROR" in severities(findings)

    def test_rate_limit_non_int_is_error(self):
        config = valid_config()
        config["forwarding"]["rate_limit_per_minute"] = "20"
        findings = validate_config(config)
        assert "ERROR" in severities(findings)

    def test_include_author_non_bool_is_error(self):
        config = valid_config()
        config["forwarding"]["include_author"] = 1
        findings = validate_config(config)
        assert "ERROR" in severities(findings)


# ---------------------------------------------------------------------------
# validate_target_number / format_whatsapp_chat_id
# ---------------------------------------------------------------------------


class TestTargetNumber:
    def test_digits_only_is_valid(self):
        assert validate_target_number("15551234567") == []

    def test_leading_plus_is_error_with_hint(self):
        findings = validate_target_number("+15551234567")
        assert "ERROR" in severities(findings)
        assert "+" in messages(findings)

    def test_spaces_and_dashes_are_error(self):
        findings = validate_target_number("1 555-123-4567")
        assert "ERROR" in severities(findings)

    def test_too_short_number_is_warning(self):
        findings = validate_target_number("12345")
        assert any(f.severity == "WARNING" for f in findings)

    def test_empty_number_is_error(self):
        findings = validate_target_number("")
        assert "ERROR" in severities(findings)

    def test_format_whatsapp_chat_id(self):
        assert format_whatsapp_chat_id("15551234567") == "15551234567@c.us"


# ---------------------------------------------------------------------------
# check_env
# ---------------------------------------------------------------------------


class TestCheckEnv:
    def test_all_present_no_findings(self):
        env = {
            "DISCORD_BOT_TOKEN": "abc123",
            "WHATSAPP_TARGET_NUMBER": "15551234567",
        }
        assert check_env(env) == []

    def test_missing_token_is_error(self):
        findings = check_env({"WHATSAPP_TARGET_NUMBER": "15551234567"})
        assert "ERROR" in severities(findings)
        assert "DISCORD_BOT_TOKEN" in messages(findings)

    def test_invalid_target_number_in_env_is_reported(self):
        env = {
            "DISCORD_BOT_TOKEN": "abc123",
            "WHATSAPP_TARGET_NUMBER": "+1 555 123 4567",
        }
        findings = check_env(env)
        assert "ERROR" in severities(findings)


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


class TestCLI:
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
        )

    def test_valid_config_exits_zero(self, tmp_path):
        config_path = tmp_path / "bridge_config.json"
        config_path.write_text(json.dumps(valid_config()))
        result = self.run_cli("--config", str(config_path), "--output-dir", str(tmp_path))
        assert result.returncode == 0

    def test_invalid_config_exits_one(self, tmp_path):
        config_path = tmp_path / "bridge_config.json"
        config_path.write_text(json.dumps({"channels": []}))
        result = self.run_cli("--config", str(config_path), "--output-dir", str(tmp_path))
        assert result.returncode == 1

    def test_missing_file_exits_one(self, tmp_path):
        result = self.run_cli("--config", str(tmp_path / "nope.json"))
        assert result.returncode == 1

    def test_malformed_json_exits_one(self, tmp_path):
        config_path = tmp_path / "bridge_config.json"
        config_path.write_text("{not json")
        result = self.run_cli("--config", str(config_path))
        assert result.returncode == 1

    def test_report_files_are_written(self, tmp_path):
        config_path = tmp_path / "bridge_config.json"
        config_path.write_text(json.dumps(valid_config()))
        out_dir = tmp_path / "reports"
        result = self.run_cli("--config", str(config_path), "--output-dir", str(out_dir))
        assert result.returncode == 0
        assert list(out_dir.glob("discord_whatsapp_bridge_check_*.md"))
        assert list(out_dir.glob("discord_whatsapp_bridge_check_*.json"))

    def test_json_report_structure(self, tmp_path):
        config_path = tmp_path / "bridge_config.json"
        config_path.write_text(json.dumps(valid_config()))
        out_dir = tmp_path / "reports"
        self.run_cli("--config", str(config_path), "--output-dir", str(out_dir))
        json_report = json.loads(next(out_dir.glob("*.json")).read_text())
        assert "findings" in json_report
        assert "valid" in json_report
        assert json_report["valid"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
