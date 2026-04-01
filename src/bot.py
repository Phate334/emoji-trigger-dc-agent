import logging

import discord

from .handlers import EmojiHandler, default_handlers

logger = logging.getLogger("emoji-trigger-agent")


class EmojiTriggerBot(discord.Client):
    def __init__(self, intents: discord.Intents, handlers: dict[str, EmojiHandler] | None = None):
        super().__init__(intents=intents)
        self.handlers = handlers or default_handlers()

    async def on_ready(self) -> None:
        if self.user is None:
            logger.info("Bot connected")
            return
        logger.info("Logged in as %s (%s)", self.user, self.user.id)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        for emoji, handler in self.handlers.items():
            if emoji in message.content:
                result = handler(message)
                await message.channel.send(result)
                logger.info(
                    "Triggered task for emoji %s in channel %s",
                    emoji,
                    message.channel.id,
                )
                break

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self.user is not None and payload.user_id == self.user.id:
            return

        emoji_text = str(payload.emoji)
        if emoji_text not in self.handlers:
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

        result = self.handlers[emoji_text](message)
        await message.channel.send(result)
        logger.info(
            "Triggered task from reaction %s in channel %s",
            emoji_text,
            payload.channel_id,
        )


def build_client() -> EmojiTriggerBot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    return EmojiTriggerBot(intents=intents)
