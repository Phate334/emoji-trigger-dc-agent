from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import discord

from .agent_manifest import AgentRoute

try:
    from codex_app_server import Codex
except ImportError:  # pragma: no cover - optional dependency in early rollout
    Codex = None


class AgentExecutor:
    async def execute(self, route: AgentRoute, message: discord.Message) -> str:
        if route.mode == "memo_append":
            return await self._append_memo(route, message)
        return await self._run_codex_turn(route, message)

    async def _append_memo(self, route: AgentRoute, message: discord.Message) -> str:
        if route.output_file is None:
            raise ValueError("memo_append mode requires 'output_file'")

        line = self._format_memo_line(message)
        await asyncio.to_thread(_append_line, route.output_file, line)
        return route.response_text

    async def _run_codex_turn(self, route: AgentRoute, message: discord.Message) -> str:
        if Codex is None:
            return "Codex SDK is not installed yet. Install dependencies and retry."
        if not route.instructions_path.exists():
            return f"Missing AGENTS instructions file: {route.instructions_path}"

        instructions = await asyncio.to_thread(route.instructions_path.read_text, "utf-8")
        prompt = self._build_prompt(instructions, message)
        return await asyncio.to_thread(_run_codex_sync, route.model, route.effort, prompt)

    @staticmethod
    def _format_memo_line(message: discord.Message) -> str:
        timestamp = datetime.now(UTC).isoformat()
        author = str(message.author)
        content = message.content.replace("\n", " ").strip()
        return f"{timestamp}\t{author}\t{content}".strip()

    @staticmethod
    def _build_prompt(instructions: str, message: discord.Message) -> str:
        return (
            "Follow the sub-agent instructions exactly.\n\n"
            f"{instructions}\n\n"
            "Incoming message context:\n"
            f"author: {message.author}\n"
            f"channel_id: {message.channel.id}\n"
            f"content: {message.content}\n"
        )


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(line)
        file.write("\n")


def _run_codex_sync(model: str, effort: str, prompt: str) -> str:
    if Codex is None:
        return "Codex SDK is not installed yet."

    with Codex() as codex:
        thread = codex.thread_start(model=model, config={"model_reasoning_effort": effort})
        result = thread.run(prompt)

    final_response = getattr(result, "final_response", None)
    if isinstance(final_response, str) and final_response.strip():
        return final_response.strip()
    return "Codex task completed."
