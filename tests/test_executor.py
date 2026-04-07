from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.agent_manifest import AgentRoute
from src.executor import AgentExecutor, ExecutionRequest, ExecutionTrigger


def _make_route(base_dir: Path, agent_id: str, emoji: str) -> AgentRoute:
    agent_dir = base_dir / "agents" / agent_id
    agent_file = agent_dir / ".claude" / "agents" / f"{agent_id}.md"
    agent_file.parent.mkdir(parents=True, exist_ok=True)
    agent_file.write_text("# test agent\n", encoding="utf-8")
    return AgentRoute(
        emoji=emoji,
        agent_id=agent_id,
        agent_dir=agent_dir,
        agent_file=agent_file,
        params={"kind": "test"},
        allowed_tools=["Read"],
    )


def _message_payload() -> dict[str, object]:
    return {
        "id": 1001,
        "content": "hello world",
        "clean_content": "hello world",
        "system_content": "",
        "jump_url": "https://discord.test/messages/1001",
        "created_at": "2026-04-05T00:00:00+00:00",
        "edited_at": None,
        "pinned": False,
        "flags": 0,
        "author": {
            "id": 42,
            "name": "alice",
            "display_name": "Alice",
            "global_name": "Alice",
            "bot": False,
        },
        "channel": {
            "id": 7,
            "name": "general",
            "type": "text",
        },
        "guild": {
            "id": 9,
            "name": "Guild",
        },
        "attachments": [],
        "embeds": [],
        "mentions": [],
        "role_mentions": [],
        "channel_mentions": [],
        "stickers": [],
        "reactions": [],
        "reference": None,
    }


class AgentExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base_dir = Path(self.tempdir.name)
        self.route = _make_route(self.base_dir, "memo-agent", "📝")
        self.executor = AgentExecutor(outputs_root=self.base_dir / "outputs")
        trigger = ExecutionTrigger(
            source="message_content",
            emoji="📝",
            user_id=None,
            observed_at="2026-04-05T00:00:00+00:00",
        )
        self.request = ExecutionRequest(
            route=self.route,
            message_payload=_message_payload(),
            trigger=trigger,
            triggers=(
                trigger,
                ExecutionTrigger(
                    source="reaction_add",
                    emoji="📌",
                    user_id=99,
                    observed_at="2026-04-05T00:00:05+00:00",
                ),
            ),
            queue_target_id=12,
            queue_attempt_count=2,
            merged_emojis=("📌", "📝"),
            queue_status="processing",
        )

    async def test_build_payload_includes_queue_metadata_and_trigger_list(self) -> None:
        payload = self.executor._build_payload(
            self.request,
            self.base_dir / "outputs" / "memo-agent",
        )

        self.assertEqual(payload["queue"]["queue_target_id"], 12)
        self.assertEqual(payload["queue"]["attempt_count"], 2)
        self.assertEqual(payload["queue"]["merged_emojis"], ["📌", "📝"])
        self.assertEqual(payload["trigger"]["emoji"], "📝")
        self.assertEqual([trigger["emoji"] for trigger in payload["triggers"]], ["📝", "📌"])

    async def test_execute_raises_when_agent_makes_no_output_changes(self) -> None:
        dummy_options = SimpleNamespace()

        with (
            patch("src.executor._sdk_query", object()),
            patch("src.executor._ClaudeAgentOptionsCls", lambda **_: dummy_options),
            patch("src.executor._run_claude_query", AsyncMock(return_value="done")),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "finished without producing any file changes",
            ):
                await self.executor.execute(self.request)
