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

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        route = self.manifest.route_for_message(message.content)
        if route is None:
            return

        result = await self.executor.execute(route, message)
        await message.channel.send(result)
        logger.info(
            "Triggered task for emoji %s in channel %s via agent %s",
            route.emoji,
            message.channel.id,
            route.agent_id,
        )

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self.user is not None and payload.user_id == self.user.id:
            return

        emoji_text = str(payload.emoji)
        route = self.manifest.route_for_reaction(emoji_text)
        if route is None:
            return

        channel = self.get_channel(payload.channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return
        except discord.Forbidden:
            logger.warning("Missing permission to fetch message %s", payload.message_id)
            return

        result = await self.executor.execute(route, message)
        await message.channel.send(result)
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
