from __future__ import annotations

import io
import json
import logging
import unittest
from unittest.mock import patch

from src.config import Settings
from src.logging_config import _derive_subsystem, log_extra, setup_logging


class LoggingConfigTests(unittest.TestCase):
    def test_setup_logging_emits_json_logs_with_extra_fields(self) -> None:
        stream = io.StringIO()
        settings = Settings(
            _env_file=None,
            discord_bot_token="discord-token",
            anthropic_api_key="real-key",
            log_format="json",
        )

        with patch("sys.stdout", stream):
            setup_logging(settings)
            logging.getLogger("test.logger").info(
                "hello world",
                extra=log_extra("test.event", target_id=12, ignored=None),
            )

        payload = json.loads(stream.getvalue().strip())
        self.assertEqual(payload["message"], "hello world")
        self.assertEqual(payload["event"], "test.event")
        self.assertEqual(payload["target_id"], 12)
        self.assertEqual(payload["logger"], "test.logger")
        self.assertEqual(payload["level"], "INFO")
        self.assertNotIn("ignored", payload)

    def test_derive_subsystem_distinguishes_claude_and_discord_loggers(self) -> None:
        claude_record = logging.makeLogRecord({"name": "emoji-trigger-agent.claude"})
        discord_record = logging.makeLogRecord({"name": "discord.gateway"})
        app_record = logging.makeLogRecord({"name": "src.executor"})

        self.assertEqual(_derive_subsystem(claude_record), "claude_sdk")
        self.assertEqual(_derive_subsystem(discord_record), "discord_py")
        self.assertEqual(_derive_subsystem(app_record), "app")
