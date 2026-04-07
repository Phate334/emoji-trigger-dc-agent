from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from src.discord_context import (
    SERIALIZED_MESSAGE_FIELD_NAMES,
    filter_message_fields,
    serialize_message,
)


class DiscordContextTests(unittest.TestCase):
    def test_serialize_message_matches_declared_top_level_fields(self) -> None:
        message = SimpleNamespace(
            id=1001,
            content="hello world",
            clean_content="hello world",
            system_content="",
            jump_url="https://discord.test/messages/1001",
            created_at=datetime(2026, 4, 5, tzinfo=UTC),
            edited_at=None,
            pinned=False,
            flags=SimpleNamespace(value=0),
            author=SimpleNamespace(
                id=42,
                name="alice",
                display_name="Alice",
                global_name="Alice",
                bot=False,
            ),
            channel=SimpleNamespace(id=7, name="general", type="text"),
            guild=SimpleNamespace(id=9, name="Guild"),
            attachments=[
                SimpleNamespace(
                    id=1,
                    filename="note.txt",
                    content_type="text/plain",
                    size=12,
                    url="https://cdn.discord.test/note.txt",
                    proxy_url="https://proxy.discord.test/note.txt",
                )
            ],
            embeds=[
                SimpleNamespace(
                    type="rich",
                    title="Example",
                    description="desc",
                    url="https://example.test",
                )
            ],
            mentions=[SimpleNamespace(id=11, name="bob", display_name="Bob")],
            role_mentions=[SimpleNamespace(id=12, name="admins")],
            channel_mentions=[SimpleNamespace(id=13, name="random", type="text")],
            stickers=[SimpleNamespace(id=14, name="wave", format="png")],
            reactions=[SimpleNamespace(emoji="📝", count=2, me=False)],
            reference=SimpleNamespace(
                message_id=2002,
                channel_id=7,
                guild_id=9,
                resolved=None,
            ),
        )

        payload = serialize_message(message)

        self.assertEqual(tuple(payload), SERIALIZED_MESSAGE_FIELD_NAMES)

    def test_filter_message_fields_keeps_requested_first_level_subset(self) -> None:
        payload = {
            "content": "hello world",
            "author": {"name": "alice"},
            "attachments": [],
            "guild": {"name": "Guild"},
        }

        filtered = filter_message_fields(payload, ["guild", "content"])

        self.assertEqual(
            filtered,
            {
                "guild": {"name": "Guild"},
                "content": "hello world",
            },
        )
