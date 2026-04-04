from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import discord

from .agent_manifest import AgentRoute

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        query,
    )
except ImportError:  # pragma: no cover - optional dependency in early rollout
    AssistantMessage = None
    ClaudeAgentOptions = None
    ResultMessage = None
    TextBlock = None
    query = None


_VALID_EFFORTS = {"low", "medium", "high", "max"}

logger = logging.getLogger("emoji-trigger-agent")


@dataclass(slots=True, frozen=True)
class TriggerContext:
    source: str
    emoji: str
    user_id: int | None = None


class AgentExecutor:
    def __init__(
        self,
        default_model_id: str | None = None,
        max_turns: int = 4,
        outputs_root: Path | str = "/app/outputs",
        sdk_env: dict[str, str] | None = None,
    ) -> None:
        self.default_model_id = default_model_id
        self.max_turns = max_turns
        self.outputs_root = Path(outputs_root)
        self.sdk_env = dict(sdk_env or {})

    async def execute(
        self,
        route: AgentRoute,
        message: discord.Message,
        trigger: TriggerContext,
    ) -> str:
        return await self._run_claude_turn(route, message, trigger)

    async def _run_claude_turn(
        self,
        route: AgentRoute,
        message: discord.Message,
        trigger: TriggerContext,
    ) -> str:
        if query is None or ClaudeAgentOptions is None:
            return "Claude Agent SDK is not installed yet. Run uv sync and retry."
        if not route.agent_file.exists():
            return f"Missing Claude agent file: {route.agent_file}"

        agent_output_dir = (self.outputs_root / route.agent_id).resolve()
        agent_output_dir.mkdir(parents=True, exist_ok=True)

        prompt = self._build_prompt(route, message, trigger, agent_output_dir)
        options = self._build_claude_options(route, agent_output_dir)
        return await _run_claude_query(prompt, options)

    def _build_claude_options(
        self,
        route: AgentRoute,
        agent_output_dir: Path,
    ) -> ClaudeAgentOptions:
        effort = route.reasoning_effort if route.reasoning_effort in _VALID_EFFORTS else None
        model_id = route.model or self.default_model_id

        def _stderr_callback(line: str) -> None:
            logger.error("Claude CLI stderr: %s", line)

        return ClaudeAgentOptions(
            cwd=route.agent_dir,
            model=model_id,
            effort=effort,
            max_turns=self.max_turns,
            permission_mode="bypassPermissions",
            setting_sources=["project"],
            add_dirs=[self.outputs_root, agent_output_dir],
            allowed_tools=route.allowed_tools or None,
            disallowed_tools=route.disallowed_tools or None,
            env=dict(self.sdk_env),
            extra_args={"agent": route.agent_id},
            stderr=_stderr_callback,
        )

    def _build_prompt(
        self,
        route: AgentRoute,
        message: discord.Message,
        trigger: TriggerContext,
        agent_output_dir: Path,
    ) -> str:
        payload = {
            "agent": {
                "agent_id": route.agent_id,
                "agent_output_dir": str(agent_output_dir),
                "route": {
                    "emoji": route.emoji,
                    "params": _normalize_json_value(route.params),
                    "model": route.model,
                    "reasoning_effort": route.reasoning_effort,
                    "allowed_tools": route.allowed_tools,
                    "disallowed_tools": route.disallowed_tools,
                },
            },
            "trigger": {
                "source": trigger.source,
                "emoji": trigger.emoji,
                "user_id": trigger.user_id,
            },
            "message": _serialize_message(message),
        }
        rendered_payload = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

        return "\n".join(
            [
                "A Discord trigger invoked the current Claude agent.",
                (
                    "Use your configured agent definition, project skills, "
                    "and project MCP setup to decide and execute the follow-up behavior."
                ),
                "The application already de-duplicates triggers by message_id + emoji.",
                (
                    "Write durable files under agent.agent_output_dir unless your route "
                    "explicitly says otherwise."
                ),
                "",
                "Discord event context (JSON):",
                rendered_payload,
            ]
        )


def _serialize_message(message: discord.Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "content": message.content,
        "clean_content": message.clean_content,
        "system_content": message.system_content,
        "jump_url": message.jump_url,
        "created_at": _serialize_datetime(message.created_at),
        "edited_at": _serialize_datetime(message.edited_at),
        "pinned": message.pinned,
        "flags": int(message.flags.value),
        "author": {
            "id": message.author.id,
            "name": message.author.name,
            "display_name": message.author.display_name,
            "global_name": getattr(message.author, "global_name", None),
            "bot": message.author.bot,
        },
        "channel": {
            "id": message.channel.id,
            "name": getattr(message.channel, "name", None),
            "type": str(message.channel.type),
        },
        "guild": {
            "id": message.guild.id,
            "name": message.guild.name,
        }
        if message.guild is not None
        else None,
        "attachments": [
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "content_type": attachment.content_type,
                "size": attachment.size,
                "url": attachment.url,
                "proxy_url": attachment.proxy_url,
            }
            for attachment in message.attachments
        ],
        "embeds": [
            {
                "type": embed.type,
                "title": embed.title,
                "description": embed.description,
                "url": embed.url,
            }
            for embed in message.embeds
        ],
        "mentions": [
            {
                "id": user.id,
                "name": user.name,
                "display_name": user.display_name,
            }
            for user in message.mentions
        ],
        "role_mentions": [
            {
                "id": role.id,
                "name": role.name,
            }
            for role in message.role_mentions
        ],
        "channel_mentions": [
            {
                "id": channel.id,
                "name": channel.name,
                "type": str(channel.type),
            }
            for channel in message.channel_mentions
        ],
        "stickers": [
            {
                "id": sticker.id,
                "name": sticker.name,
                "format": str(sticker.format),
            }
            for sticker in message.stickers
        ],
        "reactions": [
            {
                "emoji": str(reaction.emoji),
                "count": reaction.count,
                "me": reaction.me,
            }
            for reaction in message.reactions
        ],
        "reference": _serialize_message_reference(message.reference),
    }


def _serialize_message_reference(
    reference: discord.MessageReference | None,
) -> dict[str, Any] | None:
    if reference is None:
        return None

    resolved = getattr(reference, "resolved", None)
    return {
        "message_id": reference.message_id,
        "channel_id": reference.channel_id,
        "guild_id": reference.guild_id,
        "jump_url": resolved.jump_url if isinstance(resolved, discord.Message) else None,
    }


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    return value


async def _run_claude_query(prompt: str, options: ClaudeAgentOptions) -> str:
    if query is None or AssistantMessage is None or ResultMessage is None or TextBlock is None:
        return "Claude Agent SDK is not installed yet."

    assistant_fragments: list[str] = []
    final_result: str | None = None

    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        assistant_fragments.append(block.text.strip())
            elif (
                isinstance(msg, ResultMessage)
                and isinstance(msg.result, str)
                and msg.result.strip()
            ):
                final_result = msg.result.strip()
    except Exception:
        if final_result or assistant_fragments:
            logger.warning(
                "Claude query ended with non-zero exit after producing output; "
                "returning partial result",
                exc_info=True,
            )
        else:
            raise

    if final_result:
        return final_result
    if assistant_fragments:
        return "\n".join(assistant_fragments)
    return "Claude task completed."
