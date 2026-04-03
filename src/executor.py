from __future__ import annotations

import logging
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


class AgentExecutor:
    def __init__(self, default_model_id: str | None = None) -> None:
        self.default_model_id = default_model_id

    async def execute(self, route: AgentRoute, message: discord.Message) -> str:
        return await self._run_claude_turn(route, message)

    async def _run_claude_turn(self, route: AgentRoute, message: discord.Message) -> str:
        if query is None or ClaudeAgentOptions is None:
            return "Claude Agent SDK is not installed yet. Run uv sync and retry."
        if not route.agent_file.exists():
            return f"Missing Claude agent file: {route.agent_file}"

        prompt = self._build_prompt(message, route.params)
        options = self._build_claude_options(route)
        return await _run_claude_query(prompt, options)

    def _build_claude_options(self, route: AgentRoute) -> ClaudeAgentOptions:
        effort = route.reasoning_effort if route.reasoning_effort in _VALID_EFFORTS else None
        model_id = route.model or self.default_model_id

        def _stderr_callback(line: str) -> None:
            logger.error("Claude CLI stderr: %s", line)

        return ClaudeAgentOptions(
            cwd=route.agent_dir,
            model=model_id,
            effort=effort,
            max_turns=1,
            permission_mode="bypassPermissions",
            setting_sources=["project"],
            extra_args={"agent": route.agent_id},
            stderr=_stderr_callback,
        )

    @staticmethod
    def _build_prompt(
        message: discord.Message,
        params: dict[str, Any] | None = None,
    ) -> str:
        parts = [
            "A Discord emoji trigger invoked the current Claude agent.",
            (
                "Use your configured agent definition, project skills, "
                "and project MCP setup to handle this request."
            ),
            "\nIncoming message context:",
            f"author: {message.author}",
            f"channel_id: {message.channel.id}",
            f"content: {message.content}",
        ]
        if params:
            params_lines = "\n".join(f"  {k}: {v}" for k, v in params.items())
            parts.append(f"route params:\n{params_lines}")
        return "\n".join(parts)


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
