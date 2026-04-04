from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import discord

from .agent_manifest import AgentManifest, AgentRoute
from .executor import AgentExecutor, ExecutionResult, TriggerContext

logger = logging.getLogger("emoji-trigger-agent")


@dataclass(frozen=True, slots=True)
class TriggerKey:
    message_id: int
    emoji: str


class TriggerDeduper:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._completed: set[TriggerKey] = set()
        self._in_progress: set[TriggerKey] = set()

    async def begin(self, key: TriggerKey) -> bool:
        async with self._lock:
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
            logger.debug(
                "Trigger completed: %s",
                {
                    "message_id": key.message_id,
                    "emoji": key.emoji,
                    "agent_id": agent_id,
                    "channel_id": channel_id,
                    "trigger_source": trigger.source,
                    "trigger_user_id": trigger.user_id,
                },
            )

    async def abort(self, key: TriggerKey) -> None:
        async with self._lock:
            self._in_progress.discard(key)


class EmojiTriggerBot(discord.Client):
    def __init__(
        self,
        intents: discord.Intents,
        manifest: AgentManifest,
        executor: AgentExecutor,
        trigger_deduper: TriggerDeduper,
    ):
        super().__init__(intents=intents)
        self.manifest = manifest
        self.executor = executor
        self.trigger_deduper = trigger_deduper

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
        if not await self.trigger_deduper.begin(key):
            logger.info(
                "Skipping duplicate trigger for message %s emoji %s",
                message.id,
                trigger.emoji,
            )
            return

        start_time = time.monotonic()
        logger.debug(
            "Dispatching trigger: message_id=%s emoji=%s agent_id=%s channel_id=%s source=%s",
            message.id,
            trigger.emoji,
            route.agent_id,
            message.channel.id,
            trigger.source,
        )

        try:
            result = await self.executor.execute(route, message, trigger)
        except Exception:
            await self.trigger_deduper.abort(key)
            elapsed_seconds = time.monotonic() - start_time
            logger.exception("Failed to handle trigger for emoji %s", route.emoji)
            logger.debug(
                "Trigger aborted after %.1fs: message_id=%s emoji=%s agent_id=%s",
                elapsed_seconds,
                message.id,
                route.emoji,
                route.agent_id,
            )
            return

        await self.trigger_deduper.complete(
            key,
            agent_id=route.agent_id,
            channel_id=message.channel.id,
            trigger=trigger,
        )

        _log_execution_result(result)
        elapsed_seconds = time.monotonic() - start_time
        if elapsed_seconds >= 60:
            logger.warning(
                "Slow trigger execution: message_id=%s emoji=%s agent_id=%s duration=%.1fs",
                message.id,
                route.emoji,
                route.agent_id,
                elapsed_seconds,
            )

        logger.info(
            "Triggered task from %s emoji %s in channel %s via agent %s in %.1fs",
            trigger.source,
            route.emoji,
            message.channel.id,
            route.agent_id,
            elapsed_seconds,
        )


def build_client(manifest: AgentManifest, executor: AgentExecutor) -> EmojiTriggerBot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    trigger_deduper = TriggerDeduper()
    return EmojiTriggerBot(
        intents=intents,
        manifest=manifest,
        executor=executor,
        trigger_deduper=trigger_deduper,
    )


def _log_execution_result(result: ExecutionResult) -> None:
    if result.agent_output.strip():
        logger.debug("Agent output suppressed from channel: %s", result.agent_output)
    logger.debug(
        "Verified agent output files: %s",
        ", ".join(str(path) for path in result.changed_output_files),
    )
