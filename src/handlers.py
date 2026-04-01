from collections.abc import Callable

import discord

EmojiHandler = Callable[[discord.Message], str]


def handle_check_mark(message: discord.Message) -> str:
    return f"收到 ✅，任務 A 已觸發。訊息: {message.content[:80]}"


def handle_fire(message: discord.Message) -> str:
    return f"收到 🔥，任務 B 已觸發。訊息: {message.content[:80]}"


def handle_test(message: discord.Message) -> str:
    return f"收到 🧪，任務 C 已觸發。訊息: {message.content[:80]}"


def default_handlers() -> dict[str, EmojiHandler]:
    return {
        "✅": handle_check_mark,
        "🔥": handle_fire,
        "🧪": handle_test,
    }
