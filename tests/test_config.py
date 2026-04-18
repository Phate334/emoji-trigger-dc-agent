from __future__ import annotations

import unittest
from pathlib import Path

from src.config import Settings


class SettingsTests(unittest.TestCase):
    def test_trigger_queue_db_path_defaults_under_outputs_root(self) -> None:
        settings = Settings(
            _env_file=None,
            discord_bot_token="discord-token",
            anthropic_api_key="real-key",
            agent_outputs_root="outputs/runtime",
        )

        self.assertEqual(settings.agent_outputs_root, Path("outputs/runtime"))
        self.assertEqual(
            settings.resolved_trigger_queue_db_path,
            Path("outputs/runtime/trigger_queue.sqlite3"),
        )

    def test_explicit_trigger_queue_db_path_override_is_preserved(self) -> None:
        settings = Settings(
            _env_file=None,
            discord_bot_token="discord-token",
            anthropic_api_key="real-key",
            agent_outputs_root="outputs/runtime",
            trigger_queue_db_path="/tmp/custom-trigger-queue.sqlite3",
        )

        self.assertEqual(
            settings.resolved_trigger_queue_db_path,
            Path("/tmp/custom-trigger-queue.sqlite3"),
        )

    def test_claude_sdk_env_contains_only_configured_values(self) -> None:
        settings = Settings(
            _env_file=None,
            discord_bot_token="discord-token",
            anthropic_api_key="real-key",
            anthropic_auth_token="",
            anthropic_base_url="https://gateway.example.com",
        )

        self.assertEqual(
            settings.claude_sdk_env,
            {
                "ANTHROPIC_API_KEY": "real-key",
                "ANTHROPIC_BASE_URL": "https://gateway.example.com",
            },
        )

    def test_log_format_is_normalized_and_validated(self) -> None:
        settings = Settings(
            _env_file=None,
            discord_bot_token="discord-token",
            anthropic_api_key="real-key",
            log_format="TEXT",
        )

        self.assertEqual(settings.log_format, "text")

        with self.assertRaisesRegex(ValueError, "LOG_FORMAT must be one of: json, text"):
            Settings(
                _env_file=None,
                discord_bot_token="discord-token",
                anthropic_api_key="real-key",
                log_format="xml",
            )
