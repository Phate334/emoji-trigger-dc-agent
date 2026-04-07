from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from src.agent_manifest import AgentRoute
from src.executor import TriggerContext
from src.trigger_queue import TriggerQueueStore


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
        allowed_tools=["Read"],
    )


def _message_payload(message_id: int) -> dict[str, object]:
    return {
        "id": message_id,
        "content": "hello world",
        "clean_content": "hello world",
        "system_content": "",
        "jump_url": f"https://discord.test/messages/{message_id}",
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


class TriggerQueueStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base_dir = Path(self.tempdir.name)
        self.store = TriggerQueueStore(self.base_dir / "trigger_queue.sqlite3")
        self.store.initialize()
        self.message = _message_payload(1001)
        self.memo_route = _make_route(self.base_dir, "memo-agent", "📝")
        self.memo_pin_route = _make_route(self.base_dir, "memo-agent", "📌")
        self.todo_route = _make_route(self.base_dir, "todo-agent", "✅")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.store.db_path)
        connection.row_factory = sqlite3.Row
        with closing(connection) as conn:
            yield conn

    async def test_same_message_creates_one_message_row_and_two_targets(self) -> None:
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="message_content", emoji="📝"),
        )
        await self.store.enqueue_trigger(
            self.todo_route,
            self.message,
            TriggerContext(source="message_content", emoji="✅"),
        )

        with self._connect() as conn:
            message_count = conn.execute("SELECT COUNT(*) FROM queue_messages").fetchone()[0]
            target_count = conn.execute("SELECT COUNT(*) FROM queue_targets").fetchone()[0]

        self.assertEqual(message_count, 1)
        self.assertEqual(target_count, 2)

    async def test_duplicate_same_emoji_creates_one_target_and_multiple_events(self) -> None:
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="reaction_add", emoji="📝", user_id=1),
        )
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="reaction_add", emoji="📝", user_id=2),
        )

        with self._connect() as conn:
            target_count = conn.execute("SELECT COUNT(*) FROM queue_targets").fetchone()[0]
            event_count = conn.execute("SELECT COUNT(*) FROM queue_events").fetchone()[0]
            row = conn.execute("SELECT * FROM queue_targets").fetchone()

        self.assertEqual(target_count, 1)
        self.assertEqual(event_count, 2)
        self.assertEqual(json.loads(row["pending_emojis_json"]), ["📝"])

    async def test_claim_merges_multiple_emojis_for_same_agent(self) -> None:
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="message_content", emoji="📝"),
        )
        await self.store.enqueue_trigger(
            self.memo_pin_route,
            self.message,
            TriggerContext(source="reaction_add", emoji="📌", user_id=9),
        )

        item = await self.store.claim_next(claim_timeout_seconds=900)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.merged_emojis, ("📌", "📝"))
        self.assertEqual([event.emoji for event in item.trigger_events], ["📝", "📌"])

    async def test_new_emoji_while_processing_waits_for_next_round(self) -> None:
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="message_content", emoji="📝"),
        )
        first_item = await self.store.claim_next(claim_timeout_seconds=900)
        assert first_item is not None

        await self.store.enqueue_trigger(
            self.memo_pin_route,
            self.message,
            TriggerContext(source="reaction_add", emoji="📌", user_id=9),
        )
        await self.store.mark_success(first_item)

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM queue_targets").fetchone()

        self.assertEqual(row["status"], "pending")
        self.assertEqual(json.loads(row["last_finished_emojis_json"]), ["📝"])
        self.assertEqual(json.loads(row["pending_emojis_json"]), ["📌"])

        second_item = await self.store.claim_next(claim_timeout_seconds=900)
        assert second_item is not None
        self.assertEqual(second_item.merged_emojis, ("📌",))

    async def test_finished_old_emoji_does_not_reopen_but_new_emoji_does(self) -> None:
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="message_content", emoji="📝"),
        )
        item = await self.store.claim_next(claim_timeout_seconds=900)
        assert item is not None
        await self.store.mark_success(item)

        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="reaction_add", emoji="📝", user_id=88),
        )
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM queue_targets").fetchone()
            duplicate_event = conn.execute(
                """
                SELECT processed_at
                FROM queue_events
                WHERE emoji = '📝'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        self.assertEqual(row["status"], "finished")
        self.assertEqual(json.loads(row["pending_emojis_json"]), [])
        self.assertIsNotNone(duplicate_event["processed_at"])

        await self.store.enqueue_trigger(
            self.memo_pin_route,
            self.message,
            TriggerContext(source="reaction_add", emoji="📌", user_id=99),
        )
        with self._connect() as conn:
            reopened = conn.execute("SELECT * FROM queue_targets").fetchone()

        self.assertEqual(reopened["status"], "pending")
        self.assertEqual(json.loads(reopened["pending_emojis_json"]), ["📌"])

    async def test_failure_retries_then_moves_to_error(self) -> None:
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="message_content", emoji="📝"),
        )
        first_item = await self.store.claim_next(claim_timeout_seconds=900)
        assert first_item is not None
        await self.store.mark_failure(
            first_item,
            error_message="boom",
            max_retries=1,
            retry_delay_seconds=0,
        )

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM queue_targets").fetchone()

        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["attempt_count"], 1)

        second_item = await self.store.claim_next(claim_timeout_seconds=900)
        assert second_item is not None
        await self.store.mark_failure(
            second_item,
            error_message="still boom",
            max_retries=1,
            retry_delay_seconds=0,
        )

        with self._connect() as conn:
            failed = conn.execute("SELECT * FROM queue_targets").fetchone()

        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["attempt_count"], 2)
        self.assertEqual(json.loads(failed["pending_emojis_json"]), ["📝"])

    async def test_recover_expired_processing_claim(self) -> None:
        await self.store.enqueue_trigger(
            self.memo_route,
            self.message,
            TriggerContext(source="message_content", emoji="📝"),
        )
        item = await self.store.claim_next(claim_timeout_seconds=900)
        assert item is not None

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE queue_targets
                SET claim_expires_at = '2000-01-01T00:00:00+00:00'
                WHERE id = ?
                """,
                (item.target_id,),
            )
            conn.commit()

        recovered = await self.store.recover_expired_claims()

        with self._connect() as conn:
            row = conn.execute("SELECT * FROM queue_targets").fetchone()

        self.assertEqual(recovered, 1)
        self.assertEqual(row["status"], "pending")
        self.assertIsNone(row["claim_token"])
        self.assertEqual(json.loads(row["pending_emojis_json"]), ["📝"])
