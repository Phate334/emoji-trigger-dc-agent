from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src import app


class AppRunTests(unittest.TestCase):
    def test_run_disables_discord_default_log_handler(self) -> None:
        settings = SimpleNamespace(
            emoji_agent_manifest=Path("agents/agents.yaml"),
            agent_outputs_root=Path("/tmp/outputs"),
            resolved_trigger_queue_db_path=Path("/tmp/outputs/trigger_queue.sqlite3"),
            claude_model="test-model",
            claude_max_turns=4,
            claude_sdk_env={},
            trigger_queue_poll_interval_seconds=1.0,
            trigger_queue_worker_concurrency=1,
            trigger_queue_claim_timeout_seconds=900,
            trigger_queue_retry_count=3,
            trigger_queue_retry_delay_seconds=30,
            discord_bot_token="discord-token",
            log_format="json",
        )
        manifest = object()
        client = MagicMock()
        queue_store = MagicMock()

        with (
            patch("src.app.Settings", return_value=settings),
            patch("src.app.setup_logging"),
            patch("src.app._ensure_writable_directory"),
            patch("src.app.load_agent_manifest", return_value=manifest),
            patch("src.app.TriggerQueueStore", return_value=queue_store),
            patch("src.app.AgentExecutor"),
            patch("src.app.TriggerQueueWorker"),
            patch("src.app.build_client", return_value=client),
        ):
            app.run()

        client.run.assert_called_once_with("discord-token", log_handler=None)
        queue_store.initialize.assert_called_once_with()
