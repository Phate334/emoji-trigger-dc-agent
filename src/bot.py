from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

import discord

from .agent_manifest import AgentManifest, AgentRoute
from .discord_context import serialize_message
from .executor import TriggerContext
from .trigger_queue import TriggerQueueStore, TriggerQueueWorker

logger = logging.getLogger("emoji-trigger-agent")


class EmojiTriggerBot(discord.Client):
    def __init__(
        self,
        intents: discord.Intents,
        manifest: AgentManifest,
        queue_store: TriggerQueueStore,
        trigger_worker: TriggerQueueWorker,
    ) -> None:
        super().__init__(intents=intents)
        self.manifest = manifest
        self.queue_store = queue_store
        self.trigger_worker = trigger_worker

    async def setup_hook(self) -> None:
        await self.trigger_worker.start()

    async def close(self) -> None:
        await self.trigger_worker.stop()
        await super().close()

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
            logger.debug("Route loaded: emoji=%s agent_id=%s", route.emoji, route.agent_id)
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

        message_payload = serialize_message(message)
        for route in routes:
            await self._enqueue_route(
                route,
                message_payload,
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

        fetch_message = getattr(channel, "fetch_message", None)
        if fetch_message is None:
            logger.warning("Channel %s does not support fetch_message", payload.channel_id)
            return

        try:
            message = await cast(Callable[[int], Awaitable[discord.Message]], fetch_message)(
                payload.message_id
            )
        except discord.NotFound:
            logger.warning(
                "Message %s not found in channel %s", payload.message_id, payload.channel_id
            )
            return
        except discord.Forbidden:
            logger.warning("Missing permission to fetch message %s", payload.message_id)
            return

        await self._enqueue_route(
            route,
            serialize_message(message),
            TriggerContext(
                source="reaction_add",
                emoji=emoji_text,
                user_id=payload.user_id,
            ),
        )

    async def _enqueue_route(
        self,
        route: AgentRoute,
        message_payload: dict[str, object],
        trigger: TriggerContext,
    ) -> None:
        await self.queue_store.enqueue_trigger(route, dict(message_payload), trigger)
        logger.info(
            "Queued trigger from %s emoji %s for message %s via agent %s",
            trigger.source,
            route.emoji,
            message_payload["id"],
            route.agent_id,
        )


def build_client(
    manifest: AgentManifest,
    queue_store: TriggerQueueStore,
    trigger_worker: TriggerQueueWorker,
) -> EmojiTriggerBot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    return EmojiTriggerBot(
        intents=intents,
        manifest=manifest,
        queue_store=queue_store,
        trigger_worker=trigger_worker,
    )
