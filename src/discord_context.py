from __future__ import annotations

from typing import Any

import discord


def serialize_message(message: discord.Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "content": message.content,
        "clean_content": message.clean_content,
        "system_content": message.system_content,
        "jump_url": message.jump_url,
        "created_at": _serialize_datetime(message.created_at),
        "edited_at": _serialize_datetime(message.edited_at),
        "pinned": message.pinned,
        "flags": int(message.flags.value),
        "author": {
            "id": message.author.id,
            "name": message.author.name,
            "display_name": message.author.display_name,
            "global_name": getattr(message.author, "global_name", None),
            "bot": message.author.bot,
        },
        "channel": {
            "id": message.channel.id,
            "name": getattr(message.channel, "name", None),
            "type": str(message.channel.type),
        },
        "guild": {
            "id": message.guild.id,
            "name": message.guild.name,
        }
        if message.guild is not None
        else None,
        "attachments": [
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "content_type": attachment.content_type,
                "size": attachment.size,
                "url": attachment.url,
                "proxy_url": attachment.proxy_url,
            }
            for attachment in message.attachments
        ],
        "embeds": [
            {
                "type": embed.type,
                "title": embed.title,
                "description": embed.description,
                "url": embed.url,
            }
            for embed in message.embeds
        ],
        "mentions": [
            {
                "id": user.id,
                "name": user.name,
                "display_name": user.display_name,
            }
            for user in message.mentions
        ],
        "role_mentions": [
            {
                "id": role.id,
                "name": role.name,
            }
            for role in message.role_mentions
        ],
        "channel_mentions": [
            {
                "id": channel.id,
                "name": channel.name,
                "type": str(channel.type),
            }
            for channel in message.channel_mentions
        ],
        "stickers": [
            {
                "id": sticker.id,
                "name": sticker.name,
                "format": str(sticker.format),
            }
            for sticker in message.stickers
        ],
        "reactions": [
            {
                "emoji": str(reaction.emoji),
                "count": reaction.count,
                "me": reaction.me,
            }
            for reaction in message.reactions
        ],
        "reference": _serialize_message_reference(message.reference),
    }


def _serialize_message_reference(
    reference: discord.MessageReference | None,
) -> dict[str, Any] | None:
    if reference is None:
        return None

    resolved = getattr(reference, "resolved", None)
    return {
        "message_id": reference.message_id,
        "channel_id": reference.channel_id,
        "guild_id": reference.guild_id,
        "jump_url": resolved.jump_url if isinstance(resolved, discord.Message) else None,
    }


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat()
