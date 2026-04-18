from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

import discord

from .agent_manifest import AgentManifest, AgentRoute
from .discord_context import serialize_message
from .executor import TriggerContext
from .logging_config import log_extra
from .trigger_queue import TriggerQueueStore, TriggerQueueWorker

logger = logging.getLogger(__name__)


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
            logger.info("Bot connected", extra=log_extra("discord.ready"))
            return
        logger.info(
            "Logged in to Discord",
            extra=log_extra("discord.ready", bot_user=str(self.user), bot_user_id=self.user.id),
        )
        logger.info(
            "Enabled Discord intents",
            extra=log_extra(
                "discord.intents",
                message_content=self.intents.message_content,
                reactions=self.intents.reactions,
                guild_messages=self.intents.guild_messages,
                dm_messages=self.intents.dm_messages,
            ),
        )
        logger.info(
            "Loaded emoji routes",
            extra=log_extra("discord.routes.loaded", route_count=len(self.manifest.routes)),
        )
        for route in self.manifest.routes:
            logger.debug(
                "Route loaded",
                extra=log_extra(
                    "discord.route.loaded",
                    emoji=route.emoji,
                    agent_id=route.agent_id,
                ),
            )
        logger.info(
            "Connected guilds",
            extra=log_extra("discord.guilds.connected", guild_count=len(self.guilds)),
        )
        for guild in self.guilds:
            logger.info(
                "Guild connected",
                extra=log_extra(
                    "discord.guild.connected",
                    guild_id=guild.id,
                    guild_name=guild.name,
                ),
            )

    async def on_guild_join(self, guild: discord.Guild) -> None:
        logger.info(
            "Joined guild",
            extra=log_extra("discord.guild.joined", guild_id=guild.id, guild_name=guild.name),
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            logger.debug(
                "Ignoring bot-authored message",
                extra=log_extra(
                    "discord.message.ignored_bot",
                    author_id=message.author.id,
                    author_name=str(message.author),
                    channel_id=message.channel.id,
                    message_id=message.id,
                ),
            )
            return

        logger.debug(
            "Received message event",
            extra=log_extra(
                "discord.message.received",
                channel_id=message.channel.id,
                author_id=message.author.id,
                author_name=str(message.author),
                message_id=message.id,
                content_length=len(message.content),
                attachment_count=len(message.attachments),
            ),
        )

        routes = self.manifest.routes_for_message(message.content)
        if not routes:
            logger.debug(
                "Message did not match any route",
                extra=log_extra(
                    "discord.message.no_route",
                    channel_id=message.channel.id,
                    message_id=message.id,
                ),
            )
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
            logger.debug(
                "Ignoring self reaction event",
                extra=log_extra(
                    "discord.reaction.ignored_self",
                    message_id=payload.message_id,
                    channel_id=payload.channel_id,
                    user_id=payload.user_id,
                ),
            )
            return

        emoji_text = str(payload.emoji)
        logger.debug(
            "Received reaction event",
            extra=log_extra(
                "discord.reaction.received",
                emoji=emoji_text,
                channel_id=payload.channel_id,
                message_id=payload.message_id,
                user_id=payload.user_id,
            ),
        )

        route = self.manifest.route_for_reaction(emoji_text)
        if route is None:
            logger.debug(
                "Reaction did not match any route",
                extra=log_extra("discord.reaction.no_route", emoji=emoji_text),
            )
            return

        channel = self.get_channel(payload.channel_id)
        if channel is None:
            logger.debug(
                "Channel not found in cache; fetching from API",
                extra=log_extra("discord.channel.cache_miss", channel_id=payload.channel_id),
            )
            try:
                channel = await self.fetch_channel(payload.channel_id)
            except discord.NotFound:
                logger.warning(
                    "Channel not found",
                    extra=log_extra("discord.channel.not_found", channel_id=payload.channel_id),
                )
                return
            except discord.Forbidden:
                logger.warning(
                    "Missing permission to fetch channel",
                    extra=log_extra("discord.channel.forbidden", channel_id=payload.channel_id),
                )
                return

        fetch_message = getattr(channel, "fetch_message", None)
        if fetch_message is None:
            logger.warning(
                "Channel does not support fetch_message",
                extra=log_extra(
                    "discord.channel.fetch_unsupported",
                    channel_id=payload.channel_id,
                ),
            )
            return

        try:
            message = await cast(Callable[[int], Awaitable[discord.Message]], fetch_message)(
                payload.message_id
            )
        except discord.NotFound:
            logger.warning(
                "Message not found",
                extra=log_extra(
                    "discord.message.not_found",
                    message_id=payload.message_id,
                    channel_id=payload.channel_id,
                ),
            )
            return
        except discord.Forbidden:
            logger.warning(
                "Missing permission to fetch message",
                extra=log_extra(
                    "discord.message.forbidden",
                    message_id=payload.message_id,
                    channel_id=payload.channel_id,
                ),
            )
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
            "Queued trigger",
            extra=log_extra(
                "trigger.queued",
                trigger_source=trigger.source,
                emoji=route.emoji,
                message_id=message_payload.get("id"),
                channel_id=_nested_mapping_value(message_payload, "channel", "id"),
                guild_id=_nested_mapping_value(message_payload, "guild", "id"),
                agent_id=route.agent_id,
                reactor_user_id=trigger.user_id,
            ),
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


def _nested_mapping_value(
    payload: dict[str, object],
    key: str,
    nested_key: str,
) -> object | None:
    nested = payload.get(key)
    if not isinstance(nested, dict):
        return None
    return nested.get(nested_key)
