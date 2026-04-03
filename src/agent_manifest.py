from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class AgentRoute:
    emoji: str
    agent_id: str
    instructions_path: Path
    params: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    reasoning_effort: str | None = None
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
            params=_read_params(base_dir, item),
            model=_read_optional_str(item, "model"),
            reasoning_effort=_read_reasoning_effort(item),
            skill_path=_read_optional_path(base_dir, item, "skill_path"),
            mcp_profile=_read_optional_path(base_dir, item, "mcp_profile"),
        )
        _validate_route(route, index)
        routes.append(route)

    return AgentManifest(routes=routes)


def _read_optional_str(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Field '{key}' must be a non-empty string when provided")
    return value


def _read_reasoning_effort(data: dict[str, object]) -> str | None:
    # Backward compatible with legacy `effort` key.
    effort = data.get("reasoning_effort", data.get("effort"))
    if effort is None:
        return None
    if not isinstance(effort, str) or not effort:
        raise ValueError("Field 'reasoning_effort' (or legacy 'effort') must be a non-empty string")
    return effort


def _read_params(base_dir: Path, data: dict[str, object]) -> dict[str, Any]:
    raw_params = data.get("params")
    params: dict[str, Any] = {}
    if raw_params is not None:
        if not isinstance(raw_params, dict):
            raise ValueError("Field 'params' must be a mapping when provided")
        params.update(raw_params)

    output_file = params.get("output_file")
    if isinstance(output_file, str) and output_file:
        params["output_file"] = base_dir / output_file
    elif output_file is not None and not isinstance(output_file, Path):
        raise ValueError("Field 'params.output_file' must be a non-empty string when provided")

    return params


def _validate_route(route: AgentRoute, index: int) -> None:
    if not route.instructions_path.exists():
        raise ValueError(
            f"Route #{index} instructions_path does not exist: {route.instructions_path}"
        )


def _read_optional_path(base_dir: Path, data: dict[str, object], key: str) -> Path | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Field '{key}' must be a non-empty string when provided")
    return base_dir / value
