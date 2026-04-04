from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append one memo-agent markdown entry to a per-channel output file."
    )
    parser.add_argument("--event-json", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--channel-id", default="")
    parser.add_argument("--channel-name", default="")
    parser.add_argument("--guild-name", default="")
    parser.add_argument("--emoji", default="")
    parser.add_argument("--trigger-source", default="")
    parser.add_argument("--trigger-user-id", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--author-name", default="")
    parser.add_argument("--author-id", default="")
    parser.add_argument("--created-at", default="")
    parser.add_argument("--edited-at", default="")
    parser.add_argument("--jump-url", default="")
    parser.add_argument("--content", "--message-content", dest="content", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    _load_event_json(args)
    _validate_required_args(args)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _best_effort_chmod(output_dir, 0o777)
    output_file = output_dir / f"{args.channel_id}.md"

    timestamp = datetime.now(UTC).isoformat()
    channel_label = args.channel_name or "(unknown channel)"
    guild_label = args.guild_name or "(no guild)"
    trigger_source = args.trigger_source or "(unknown source)"
    trigger_user_label = args.trigger_user_id or "(not provided)"
    message_id = args.message_id or "(unknown message id)"
    author_name = args.author_name or "(unknown author)"
    author_id = args.author_id or "(unknown author id)"
    created_at = args.created_at or "(unknown created_at)"
    edited_at = args.edited_at or "(not edited)"
    content = args.content if args.content else "(empty message)"

    entry_lines = [
        f"## {timestamp} | {args.emoji} | message {message_id}",
        f"- Trigger source: {trigger_source}",
        f"- Trigger user id: {trigger_user_label}",
        f"- Author: {author_name} ({author_id})",
        f"- Channel: {channel_label} ({args.channel_id})",
        f"- Guild: {guild_label}",
        f"- Message created at: {created_at}",
        f"- Message edited at: {edited_at}",
        f"- Jump URL: {args.jump_url or '(not available)'}",
        "",
        "Message:",
        "~~~text",
        content,
        "~~~",
        "",
    ]

    needs_header = not output_file.exists()
    with output_file.open("a", encoding="utf-8") as file:
        if needs_header:
            file.write(f"# Memo Agent Output for Channel {args.channel_id}\n\n")
        file.write("\n".join(entry_lines))
    _best_effort_chmod(output_file, 0o666)

    print(output_file)


def _load_event_json(args: argparse.Namespace) -> None:
    if not args.event_json:
        return

    payload = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    agent = _as_dict(payload.get("agent"))
    trigger = _as_dict(payload.get("trigger"))
    message = _as_dict(payload.get("message"))
    author = _as_dict(message.get("author"))
    channel = _as_dict(message.get("channel"))
    guild = _as_dict(message.get("guild"))

    args.output_dir = _as_text(agent.get("agent_output_dir"))
    args.channel_id = _as_text(channel.get("id"))
    args.channel_name = _as_text(channel.get("name"))
    args.guild_name = _as_text(guild.get("name"))
    args.emoji = _as_text(trigger.get("emoji"))
    args.trigger_source = _as_text(trigger.get("source"))
    args.trigger_user_id = _as_text(trigger.get("user_id"))
    args.message_id = _as_text(message.get("id"))
    author_name = author.get("display_name") or author.get("name")
    args.author_name = _as_text(author_name)
    args.author_id = _as_text(author.get("id"))
    args.created_at = _as_text(message.get("created_at"))
    args.edited_at = _as_text(message.get("edited_at"))
    args.jump_url = _as_text(message.get("jump_url"))
    args.content = _as_text(message.get("content"))


def _validate_required_args(args: argparse.Namespace) -> None:
    missing: list[str] = []
    if not args.output_dir:
        missing.append("--output-dir")
    if not args.channel_id:
        missing.append("--channel-id")
    if not args.emoji:
        missing.append("--emoji")
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"Missing required values: {joined}")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _best_effort_chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


if __name__ == "__main__":
    main()
