from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from textwrap import dedent

from src.agent_manifest import load_agent_manifest


class AgentManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base_dir = Path(self.tempdir.name)
        self.agents_dir = self.base_dir / "agents"
        self.agents_dir.mkdir()
        self._create_agent("memo-agent")
        self._create_agent("todo-agent")

    def _create_agent(self, agent_id: str) -> None:
        agent_file = self.agents_dir / agent_id / ".claude" / "agents" / f"{agent_id}.md"
        agent_file.parent.mkdir(parents=True, exist_ok=True)
        agent_file.write_text("# test agent\n", encoding="utf-8")

    def _write_manifest(self, body: str) -> Path:
        manifest_path = self.agents_dir / "agents.yaml"
        manifest_path.write_text(dedent(body).strip() + "\n", encoding="utf-8")
        return manifest_path

    def test_message_fields_defaults_to_full_message_payload(self) -> None:
        manifest_path = self._write_manifest(
            """
            version: 1
            routes:
              - emoji: "📝"
                agent_id: "memo-agent"
            """
        )

        manifest = load_agent_manifest(manifest_path)

        self.assertIsNone(manifest.routes[0].message_fields)

    def test_message_fields_accepts_valid_top_level_fields(self) -> None:
        manifest_path = self._write_manifest(
            """
            version: 1
            routes:
              - emoji: "📝"
                agent_id: "memo-agent"
                message_fields:
                  - "content"
                  - "author"
                  - "attachments"
            """
        )

        manifest = load_agent_manifest(manifest_path)

        self.assertEqual(
            manifest.routes[0].message_fields,
            ["content", "author", "attachments"],
        )

    def test_message_fields_rejects_invalid_values(self) -> None:
        cases = {
            "empty list": """
                version: 1
                routes:
                  - emoji: "📝"
                    agent_id: "memo-agent"
                    message_fields: []
            """,
            "empty string": """
                version: 1
                routes:
                  - emoji: "📝"
                    agent_id: "memo-agent"
                    message_fields:
                      - ""
            """,
            "duplicate": """
                version: 1
                routes:
                  - emoji: "📝"
                    agent_id: "memo-agent"
                    message_fields:
                      - "content"
                      - "content"
            """,
            "unsupported": """
                version: 1
                routes:
                  - emoji: "📝"
                    agent_id: "memo-agent"
                    message_fields:
                      - "author.display_name"
            """,
        }

        for label, body in cases.items():
            with self.subTest(case=label):
                manifest_path = self._write_manifest(body)
                with self.assertRaisesRegex(ValueError, "message_fields"):
                    load_agent_manifest(manifest_path)

    def test_removed_tool_policy_fields_raise_error(self) -> None:
        for field_name in ("allowed_tools", "disallowed_tools"):
            with self.subTest(field=field_name):
                manifest_path = self._write_manifest(
                    f"""
                    version: 1
                    routes:
                      - emoji: "📝"
                        agent_id: "memo-agent"
                        {field_name}:
                          - "Read"
                    """
                )

                with self.assertRaisesRegex(ValueError, field_name):
                    load_agent_manifest(manifest_path)

    def test_shared_agent_requires_identical_message_fields(self) -> None:
        manifest_path = self._write_manifest(
            """
            version: 1
            routes:
              - emoji: "📝"
                agent_id: "memo-agent"
                message_fields:
                  - "content"
              - emoji: "📌"
                agent_id: "memo-agent"
                message_fields:
                  - "author"
            """
        )

        with self.assertRaisesRegex(ValueError, "message_fields"):
            load_agent_manifest(manifest_path)
