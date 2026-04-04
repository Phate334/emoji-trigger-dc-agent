from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import discord

from .agent_manifest import AgentManifest, AgentRoute
from .executor import AgentExecutor, TriggerContext

logger = logging.getLogger("emoji-trigger-agent")


@dataclass(frozen=True, slots=True)
class TriggerKey:
    message_id: int
    emoji: str


class TriggerLedger:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self._loaded = False
        self._lock = asyncio.Lock()
        self._completed: set[TriggerKey] = set()
        self._in_progress: set[TriggerKey] = set()

    async def begin(self, key: TriggerKey) -> bool:
        async with self._lock:
            self._load_if_needed()
            if key in self._completed or key in self._in_progress:
                return False
            self._in_progress.add(key)
            return True

    async def complete(
        self,
        key: TriggerKey,
        *,
        agent_id: str,
        channel_id: int,
        trigger: TriggerContext,
    ) -> None:
        async with self._lock:
            self._completed.add(key)
            self._in_progress.discard(key)
            self._append_record(
                {
                    "processed_at": datetime.now(UTC).isoformat(),
                    "message_id": key.message_id,
                    "emoji": key.emoji,
                    "agent_id": agent_id,
                    "channel_id": channel_id,
                    "trigger_source": trigger.source,
                    "trigger_user_id": trigger.user_id,
                }
            )

    async def abort(self, key: TriggerKey) -> None:
        async with self._lock:
            self._in_progress.discard(key)

    def _load_if_needed(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.state_file.is_file():
            return

        with self.state_file.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed trigger ledger line: %s", line)
                    continue
                message_id = item.get("message_id")
                emoji = item.get("emoji")
                if isinstance(message_id, int) and isinstance(emoji, str) and emoji:
                    self._completed.add(TriggerKey(message_id=message_id, emoji=emoji))

    def _append_record(self, record: dict[str, object]) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with self.state_file.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("Failed to persist trigger ledger record to %s", self.state_file)


class EmojiTriggerBot(discord.Client):
    def __init__(
        self,
        intents: discord.Intents,
        manifest: AgentManifest,
        executor: AgentExecutor,
        trigger_ledger: TriggerLedger,
    ):
        super().__init__(intents=intents)
        self.manifest = manifest
        self.executor = executor
        self.trigger_ledger = trigger_ledger

    async def on_ready(self) -> None:
        if self.user is None:
            logger.info("Bot connected")
            return
        logger.info("Logged in as %s (%s)", self.user, self.user.id)
        logger.info(
            "Enabled intents: message_content=%s reactions=%s guild_messages=%s dm_messages=%s",
            self.intents.message_content,
            self.intents.reactions,
            self.intents.guild_messages,
            self.intents.dm_messages,
        )
        logger.info("Loaded %s emoji route(s)", len(self.manifest.routes))
        for route in self.manifest.routes:
            logger.debug(
                "Route loaded: emoji=%s agent_id=%s",
                route.emoji,
                route.agent_id,
            )
        logger.info("Connected guilds: %s", len(self.guilds))
        for guild in self.guilds:
            logger.info("Guild connected: %s (%s)", guild.name, guild.id)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        logger.info("Joined guild: %s (%s)", guild.name, guild.id)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            logger.debug("Ignoring bot message from %s", message.author)
            return

        logger.debug(
            "Message event: channel=%s author=%s content=%r",
            message.channel.id,
            message.author,
            message.content,
        )

        routes = self.manifest.routes_for_message(message.content)
        if not routes:
            logger.debug("No route matched message content in channel %s", message.channel.id)
            return

        for route in routes:
            await self._dispatch_route(
                route,
                message,
                TriggerContext(source="message_content", emoji=route.emoji),
            )

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self.user is not None and payload.user_id == self.user.id:
            logger.debug("Ignoring self reaction event on message %s", payload.message_id)
            return

        emoji_text = str(payload.emoji)
        logger.debug(
            "Reaction event: emoji=%s channel=%s message=%s user=%s",
            emoji_text,
            payload.channel_id,
            payload.message_id,
            payload.user_id,
        )

        route = self.manifest.route_for_reaction(emoji_text)
        if route is None:
            logger.debug("No route matched reaction emoji=%s", emoji_text)
            return

        channel = self.get_channel(payload.channel_id)
        if channel is None:
            logger.debug("Channel %s not found in cache, fetching from API", payload.channel_id)
            try:
                channel = await self.fetch_channel(payload.channel_id)
            except discord.NotFound:
                logger.warning("Channel %s not found", payload.channel_id)
                return
            except discord.Forbidden:
                logger.warning("Missing permission to fetch channel %s", payload.channel_id)
                return

        if not hasattr(channel, "fetch_message"):
            logger.warning("Channel %s does not support fetch_message", payload.channel_id)
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            logger.warning(
                "Message %s not found in channel %s", payload.message_id, payload.channel_id
            )
            return
        except discord.Forbidden:
            logger.warning("Missing permission to fetch message %s", payload.message_id)
            return

        await self._dispatch_route(
            route,
            message,
            TriggerContext(
                source="reaction_add",
                emoji=emoji_text,
                user_id=payload.user_id,
            ),
        )

    async def _dispatch_route(
        self,
        route: AgentRoute,
        message: discord.Message,
        trigger: TriggerContext,
    ) -> None:
        key = TriggerKey(message_id=message.id, emoji=trigger.emoji)
        if not await self.trigger_ledger.begin(key):
            logger.info(
                "Skipping duplicate trigger for message %s emoji %s",
                message.id,
                trigger.emoji,
            )
            return

        try:
            result = await self.executor.execute(route, message, trigger)
        except Exception:
            await self.trigger_ledger.abort(key)
            logger.exception("Failed to handle trigger for emoji %s", route.emoji)
            return

        await self.trigger_ledger.complete(
            key,
            agent_id=route.agent_id,
            channel_id=message.channel.id,
            trigger=trigger,
        )

        if result.strip():
            logger.debug("Agent output suppressed from channel: %s", result)

        logger.info(
            "Triggered task from %s emoji %s in channel %s via agent %s",
            trigger.source,
            route.emoji,
            message.channel.id,
            route.agent_id,
        )


def build_client(manifest: AgentManifest, executor: AgentExecutor) -> EmojiTriggerBot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    trigger_ledger = TriggerLedger(executor.outputs_root / ".state" / "processed-triggers.jsonl")
    return EmojiTriggerBot(
        intents=intents,
        manifest=manifest,
        executor=executor,
        trigger_ledger=trigger_ledger,
    )
