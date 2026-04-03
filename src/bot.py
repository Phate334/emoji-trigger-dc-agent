import logging

import discord

from .agent_manifest import AgentManifest
from .executor import AgentExecutor

logger = logging.getLogger("emoji-trigger-agent")


class EmojiTriggerBot(discord.Client):
    def __init__(self, intents: discord.Intents, manifest: AgentManifest, executor: AgentExecutor):
        super().__init__(intents=intents)
        self.manifest = manifest
        self.executor = executor

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
                "Route loaded: emoji=%s agent_id=%s mode=%s",
                route.emoji,
                route.agent_id,
                route.mode,
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

        route = self.manifest.route_for_message(message.content)
        if route is None:
            logger.debug("No route matched message content in channel %s", message.channel.id)
            return

        try:
            result = await self.executor.execute(route, message)
            await message.channel.send(result)
        except Exception:
            logger.exception("Failed to handle message trigger for emoji %s", route.emoji)
            return

        logger.info(
            "Triggered task for emoji %s in channel %s via agent %s",
            route.emoji,
            message.channel.id,
            route.agent_id,
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

        try:
            result = await self.executor.execute(route, message)
            await message.channel.send(result)
        except Exception:
            logger.exception("Failed to handle reaction trigger for emoji %s", route.emoji)
            return

        logger.info(
            "Triggered task from reaction %s in channel %s via agent %s",
            route.emoji,
            payload.channel_id,
            route.agent_id,
        )


def build_client(manifest: AgentManifest, executor: AgentExecutor) -> EmojiTriggerBot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    return EmojiTriggerBot(intents=intents, manifest=manifest, executor=executor)
