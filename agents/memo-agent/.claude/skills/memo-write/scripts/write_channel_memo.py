from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append one memo-agent markdown entry to a per-channel output file."
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument("--channel-name", default="")
    parser.add_argument("--guild-name", default="")
    parser.add_argument("--emoji", required=True)
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


def _best_effort_chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        pass


if __name__ == "__main__":
    main()
