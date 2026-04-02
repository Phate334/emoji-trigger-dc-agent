from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class AgentRoute:
    emoji: str
    agent_id: str
    instructions_path: Path
    mode: str = "codex_turn"
    response_text: str = "Task completed."
    output_file: Path | None = None
    model: str = "gpt-5.4"
    effort: str = "medium"
    skill_path: Path | None = None
    mcp_profile: Path | None = None


@dataclass(slots=True)
class AgentManifest:
    routes: list[AgentRoute]

    def route_for_message(self, content: str) -> AgentRoute | None:
        for route in self.routes:
            if route.emoji in content:
                return route
        return None

    def route_for_reaction(self, emoji_text: str) -> AgentRoute | None:
        for route in self.routes:
            if route.emoji == emoji_text:
                return route
        return None


def load_agent_manifest(path: Path) -> AgentManifest:
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    raw_routes = raw.get("routes")
    if not isinstance(raw_routes, list) or not raw_routes:
        raise ValueError("Manifest must contain a non-empty 'routes' list")

    base_dir = path.parent.parent
    routes: list[AgentRoute] = []

    for index, item in enumerate(raw_routes, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Route #{index} is not a mapping")

        emoji = item.get("emoji")
        agent_id = item.get("agent_id")
        instructions_rel = item.get("instructions_path")

        if not isinstance(emoji, str) or not emoji:
            raise ValueError(f"Route #{index} is missing 'emoji'")
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError(f"Route #{index} is missing 'agent_id'")
        if not isinstance(instructions_rel, str) or not instructions_rel:
            raise ValueError(f"Route #{index} is missing 'instructions_path'")

        route = AgentRoute(
            emoji=emoji,
            agent_id=agent_id,
            instructions_path=base_dir / instructions_rel,
            mode=_read_str(item, "mode", "codex_turn"),
            response_text=_read_str(item, "response_text", "Task completed."),
            output_file=_read_optional_path(base_dir, item, "output_file"),
            model=_read_str(item, "model", "gpt-5.4"),
            effort=_read_str(item, "effort", "medium"),
            skill_path=_read_optional_path(base_dir, item, "skill_path"),
            mcp_profile=_read_optional_path(base_dir, item, "mcp_profile"),
        )
        routes.append(route)

    return AgentManifest(routes=routes)


def _read_str(data: dict[str, object], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"Field '{key}' must be a string")
    return value


def _read_optional_path(base_dir: Path, data: dict[str, object], key: str) -> Path | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Field '{key}' must be a non-empty string when provided")
    return base_dir / value
