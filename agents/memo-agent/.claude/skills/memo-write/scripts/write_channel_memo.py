from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class MemoEvent:
    output_dir: Path
    channel_id: str
    channel_name: str
    guild_name: str
    message_id: str
    author_name: str
    author_id: str
    created_at: str
    edited_at: str
    jump_url: str
    content: str

    @property
    def channel_label(self) -> str:
        return self.channel_name or f"channel-{self.channel_id}"

    @property
    def preferred_output_file(self) -> Path:
        return self.output_dir / f"{_safe_file_stem(self.channel_name, self.channel_id)}.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Upsert one memo-agent markdown topic section into a per-channel output file."
    )
    parser.add_argument("--event-json", required=True)
    parser.add_argument("--section-title", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    event = _load_memo_event(args.event_json)

    event.output_dir.mkdir(parents=True, exist_ok=True)
    _best_effort_chmod(event.output_dir, 0o777)

    output_file = _resolve_output_file(event)
    existing_text = output_file.read_text(encoding="utf-8") if output_file.exists() else ""
    document_text = _ensure_document_header(existing_text, event)
    section_title = _derive_section_title(args.section_title, event.content)
    existing_body = _extract_section_body(document_text, section_title)
    section_body = _render_section(section_title, event, existing_body)
    updated_text = _upsert_section(document_text, section_title, section_body)

    output_file.write_text(updated_text, encoding="utf-8")
    _best_effort_chmod(output_file, 0o666)
    print(output_file)


def _load_memo_event(event_json_path: str) -> MemoEvent:
    payload = json.loads(Path(event_json_path).read_text(encoding="utf-8"))
    agent = _as_dict(payload.get("agent"))
    message = _as_dict(payload.get("message"))
    author = _as_dict(message.get("author"))
    channel = _as_dict(message.get("channel"))
    guild = _as_dict(message.get("guild"))

    output_dir = Path(_required_text(agent.get("agent_output_dir"), "agent.agent_output_dir"))
    channel_id = _required_text(channel.get("id"), "message.channel.id")

    return MemoEvent(
        output_dir=output_dir,
        channel_id=channel_id,
        channel_name=_as_text(channel.get("name")),
        guild_name=_as_text(guild.get("name")),
        message_id=_as_text(message.get("id")),
        author_name=_as_text(author.get("display_name") or author.get("name")),
        author_id=_as_text(author.get("id")),
        created_at=_as_text(message.get("created_at")),
        edited_at=_as_text(message.get("edited_at")),
        jump_url=_as_text(message.get("jump_url")),
        content=_as_text(message.get("content")),
    )


def _ensure_document_header(existing_text: str, event: MemoEvent) -> str:
    desired_header = _render_document_header(event)
    body = _strip_existing_document_header(existing_text)
    if body:
        return f"{desired_header}\n\n{body}\n"
    return f"{desired_header}\n"


def _render_document_header(event: MemoEvent) -> str:
    guild_label = event.guild_name or "direct-message"
    return "\n".join(
        [
            f"# {event.channel_label}",
            "",
            f"_Channel `{event.channel_id}` in {guild_label}._",
        ]
    )


def _derive_section_title(section_title: str, content: str) -> str:
    normalized = _normalize_heading_text(section_title)
    if normalized:
        return normalized

    for line in content.splitlines():
        cleaned = _normalize_heading_text(line)
        cleaned = re.sub(r"https?://\S+", "", cleaned).strip(" -")
        if cleaned:
            return cleaned[:80].rstrip()

    return "General Notes"


def _render_section(
    section_title: str,
    event: MemoEvent,
    existing_body: list[str],
) -> str:
    message_entry = _render_message_entry(event)
    body_lines = _merge_section_body(existing_body, message_entry)
    lines = [f"## {section_title}", *body_lines]
    return "\n".join(lines).rstrip() + "\n"


def _extract_section_body(document_text: str, section_title: str) -> list[str]:
    lines = document_text.splitlines()
    section_range = _find_section_range(lines, section_title)
    if section_range is None:
        return []
    start, end = section_range
    return lines[start + 1 : end]


def _merge_section_body(existing_body: list[str], message_entry: str) -> list[str]:
    body = [line for line in existing_body if line.strip() != "### Collected Messages"]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    entry_lines = message_entry.rstrip("\n").splitlines()
    if not body:
        return ["", *entry_lines]

    merged = ["", *body, "", *entry_lines]
    return merged


def _render_message_entry(event: MemoEvent) -> str:
    timestamp = event.created_at or datetime.now(UTC).isoformat()
    author_name = _single_line_text(event.author_name) or "(unknown author)"
    author_id = _single_line_text(event.author_id)
    author_label = f"{author_name} ({author_id})" if author_id else author_name
    message_id = event.message_id or "(unknown message id)"
    source_label = (
        f"[Discord message {message_id}]({event.jump_url})"
        if event.jump_url
        else f"Discord message {message_id}"
    )

    lines = [
        f"### {timestamp} | {author_label}",
        f"- Source: {source_label}",
    ]
    if event.edited_at:
        lines.append(f"- Edited at: {event.edited_at}")
    lines.extend(["", _format_blockquote(event.content)])
    return "\n".join(lines).rstrip() + "\n"


def _upsert_section(document_text: str, section_title: str, section_body: str) -> str:
    lines = document_text.splitlines()
    section_lines = section_body.rstrip("\n").splitlines()
    section_range = _find_section_range(lines, section_title)

    if section_range is None:
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            lines.append("")
        lines.extend(section_lines)
        return "\n".join(lines).rstrip() + "\n"

    start, end = section_range
    before = lines[:start]
    after = lines[end:]

    while before and not before[-1].strip():
        before.pop()
    while after and not after[0].strip():
        after.pop(0)

    merged: list[str] = []
    if before:
        merged.extend(before)
        merged.append("")
    merged.extend(section_lines)
    if after:
        merged.append("")
        merged.extend(after)
    return "\n".join(merged).rstrip() + "\n"


def _find_section_range(lines: list[str], section_title: str) -> tuple[int, int] | None:
    target_key = _section_key(section_title)
    start_index: int | None = None

    for index, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        if _section_key(line[3:]) == target_key:
            start_index = index
            break

    if start_index is None:
        return None

    end_index = len(lines)
    for index in range(start_index + 1, len(lines)):
        if lines[index].startswith("## "):
            end_index = index
            break

    return start_index, end_index


def _section_key(value: str) -> str:
    return _normalize_heading_text(value).casefold()


def _resolve_output_file(event: MemoEvent) -> Path:
    output_file = event.preferred_output_file
    if not output_file.exists():
        return output_file

    existing_channel_id = _extract_document_channel_id(output_file.read_text(encoding="utf-8"))
    if not existing_channel_id or existing_channel_id == event.channel_id:
        return output_file

    fallback_stem = f"{output_file.stem}--{event.channel_id}"
    return output_file.with_name(f"{fallback_stem}.md")


def _strip_existing_document_header(text: str) -> str:
    if not text.strip():
        return ""

    lines = text.splitlines()
    first_non_empty_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first_non_empty_index is None:
        return ""

    if not lines[first_non_empty_index].startswith("# "):
        return text.strip()

    body_start = first_non_empty_index + 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    if body_start < len(lines) and lines[body_start].startswith("_Channel `"):
        body_start += 1

    return "\n".join(lines[body_start:]).strip()


def _extract_document_channel_id(text: str) -> str:
    match = re.search(r"_Channel `([^`]+)` in .*?\._", text)
    return match.group(1) if match else ""


def _normalize_heading_text(value: str) -> str:
    value = re.sub(r"^#+\s*", "", value or "").strip()
    return re.sub(r"\s+", " ", value)


def _single_line_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _safe_file_stem(channel_name: str, channel_id: str) -> str:
    candidate = _single_line_text(channel_name)
    if not candidate:
        return f"channel-{channel_id}"

    candidate = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" .")
    return candidate or f"channel-{channel_id}"


def _format_blockquote(content: str) -> str:
    raw = (content or "").strip()
    if not raw:
        return "> (empty message)"

    lines: list[str] = []
    total_chars = 0
    truncated = False
    for current_line in raw.splitlines():
        candidate = current_line.rstrip()
        total_chars += len(candidate)
        if len(lines) >= 12 or total_chars > 1200:
            truncated = True
            break
        lines.append(candidate)

    if not lines:
        return "> (empty message)"

    if truncated:
        lines.append("...")

    return "\n".join("> " if not line else f"> {line}" for line in lines)


def _required_text(value: Any, field_name: str) -> str:
    text = _as_text(value)
    if text:
        return text
    raise SystemExit(f"Missing required runtime field: {field_name}")


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
