from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class AgentRoute:
    emoji: str
    agent_id: str
    agent_dir: Path
    agent_file: Path
    params: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    reasoning_effort: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentManifest:
    routes: list[AgentRoute]

    def routes_for_message(self, content: str) -> list[AgentRoute]:
        return [route for route in self.routes if route.emoji in content]

    def route_for_message(self, content: str) -> AgentRoute | None:
        routes = self.routes_for_message(content)
        if routes:
            return routes[0]
        return None

    def route_for_reaction(self, emoji_text: str) -> AgentRoute | None:
        for route in self.routes:
            if route.emoji == emoji_text:
                return route
        return None

    def execution_route_for_agent(self, agent_id: str) -> AgentRoute | None:
        for route in self.routes:
            if route.agent_id == agent_id:
                return route
        return None


def load_agent_manifest(path: Path) -> AgentManifest:
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    raw_routes = raw.get("routes")
    if not isinstance(raw_routes, list) or not raw_routes:
        raise ValueError("Manifest must contain a non-empty 'routes' list")

    agents_dir = path.parent
    routes: list[AgentRoute] = []
    seen_emojis: set[str] = set()
    agent_profiles: dict[str, AgentRoute] = {}

    for index, item in enumerate(raw_routes, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Route #{index} is not a mapping")

        emoji = item.get("emoji")
        agent_id = item.get("agent_id")

        if not isinstance(emoji, str) or not emoji:
            raise ValueError(f"Route #{index} is missing 'emoji'")
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError(f"Route #{index} is missing 'agent_id'")
        if emoji in seen_emojis:
            raise ValueError(f"Route #{index} reuses emoji already assigned earlier: {emoji}")

        agent_dir = (agents_dir / agent_id).resolve()
        agent_file = (agent_dir / ".claude" / "agents" / f"{agent_id}.md").resolve()

        route = AgentRoute(
            emoji=emoji,
            agent_id=agent_id,
            agent_dir=agent_dir,
            agent_file=agent_file,
            params=_read_params(item),
            model=_read_optional_str(item, "model"),
            reasoning_effort=_read_reasoning_effort(item),
            allowed_tools=_read_optional_str_list(item, "allowed_tools"),
            disallowed_tools=_read_optional_str_list(item, "disallowed_tools"),
        )
        _validate_route(route, index)
        existing_profile = agent_profiles.get(agent_id)
        if existing_profile is not None and not _same_execution_profile(existing_profile, route):
            raise ValueError(
                "Routes that share the same 'agent_id' must use the same params, model, "
                "reasoning_effort, allowed_tools, and disallowed_tools so they can be merged "
                "into one queued execution target"
            )
        routes.append(route)
        seen_emojis.add(emoji)
        agent_profiles.setdefault(agent_id, route)

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


def _read_optional_str_list(data: dict[str, object], key: str) -> list[str]:
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Field '{key}' must be a list of non-empty strings when provided")

    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"Field '{key}' must contain only non-empty strings")
        items.append(item)
    return items


def _read_params(data: dict[str, object]) -> dict[str, Any]:
    raw_params = data.get("params")
    params: dict[str, Any] = {}
    if raw_params is not None:
        if not isinstance(raw_params, dict):
            raise ValueError("Field 'params' must be a mapping when provided")
        params.update(raw_params)

    return params


def _validate_route(route: AgentRoute, index: int) -> None:
    if not route.agent_dir.is_dir():
        raise ValueError(f"Route #{index} agent directory does not exist: {route.agent_dir}")
    if not route.agent_file.is_file():
        raise ValueError(f"Route #{index} agent file does not exist: {route.agent_file}")


def _same_execution_profile(left: AgentRoute, right: AgentRoute) -> bool:
    return (
        left.agent_id == right.agent_id
        and left.agent_dir == right.agent_dir
        and left.agent_file == right.agent_file
        and left.params == right.params
        and left.model == right.model
        and left.reasoning_effort == right.reasoning_effort
        and left.allowed_tools == right.allowed_tools
        and left.disallowed_tools == right.disallowed_tools
    )
