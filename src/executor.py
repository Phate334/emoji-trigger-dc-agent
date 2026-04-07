from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any, Literal, cast

from .agent_manifest import AgentRoute

if TYPE_CHECKING:
    from claude_agent_sdk import ClaudeAgentOptions as ClaudeAgentOptionsT
else:
    ClaudeAgentOptionsT = Any

_claude_agent_sdk: Any | None

try:
    _claude_agent_sdk = import_module("claude_agent_sdk")
except ImportError:  # pragma: no cover - optional dependency in early rollout
    _claude_agent_sdk = None

_AssistantMessageCls = getattr(_claude_agent_sdk, "AssistantMessage", None)
_ClaudeAgentOptionsCls = getattr(_claude_agent_sdk, "ClaudeAgentOptions", None)
_ResultMessageCls = getattr(_claude_agent_sdk, "ResultMessage", None)
_TextBlockCls = getattr(_claude_agent_sdk, "TextBlock", None)
_sdk_query = getattr(_claude_agent_sdk, "query", None)


type ReasoningEffort = Literal["low", "medium", "high", "max"]

_VALID_EFFORTS = frozenset({"low", "medium", "high", "max"})

logger = logging.getLogger("emoji-trigger-agent")


@dataclass(slots=True, frozen=True)
class TriggerContext:
    source: str
    emoji: str
    user_id: int | None = None
    observed_at: str | None = None


@dataclass(slots=True, frozen=True)
class ExecutionTrigger:
    source: str
    emoji: str
    user_id: int | None = None
    observed_at: str | None = None


@dataclass(slots=True, frozen=True)
class ExecutionRequest:
    route: AgentRoute
    message_payload: dict[str, Any]
    trigger: ExecutionTrigger
    triggers: tuple[ExecutionTrigger, ...]
    queue_target_id: int
    queue_attempt_count: int
    merged_emojis: tuple[str, ...]
    queue_status: str


@dataclass(slots=True, frozen=True)
class ExecutionResult:
    agent_output: str
    changed_output_files: tuple[Path, ...]


class AgentExecutor:
    def __init__(
        self,
        default_model_id: str | None = None,
        max_turns: int = 4,
        outputs_root: Path | str = "/app/outputs",
        sdk_env: dict[str, str] | None = None,
    ) -> None:
        self.default_model_id = default_model_id
        self.max_turns = max_turns
        self.outputs_root = Path(outputs_root)
        self.sdk_env = dict(sdk_env or {})

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return await self._run_claude_turn(request)

    async def _run_claude_turn(self, request: ExecutionRequest) -> ExecutionResult:
        route = request.route
        if _sdk_query is None or _ClaudeAgentOptionsCls is None:
            raise RuntimeError("Claude Agent SDK is not installed yet. Run uv sync and retry.")
        if not route.agent_file.exists():
            raise RuntimeError(f"Missing Claude agent file: {route.agent_file}")

        agent_output_dir = (self.outputs_root / route.agent_id).resolve()
        agent_output_dir.mkdir(parents=True, exist_ok=True)
        before_snapshot = _snapshot_output_tree(agent_output_dir)
        payload = self._build_payload(request, agent_output_dir)
        runtime_context_file = _write_runtime_context_file(route.agent_dir, payload)

        try:
            prompt = self._build_prompt(payload, runtime_context_file)
            options = self._build_claude_options(route, agent_output_dir)
            agent_output = await _run_claude_query(prompt, options)
            changed_output_files = _detect_output_changes(agent_output_dir, before_snapshot)
            if not changed_output_files:
                if agent_output.strip():
                    logger.error("Claude agent returned without file changes: %s", agent_output)
                raise RuntimeError(
                    "Claude agent finished without producing any file changes under "
                    f"{agent_output_dir}"
                )

            return ExecutionResult(
                agent_output=agent_output,
                changed_output_files=changed_output_files,
            )
        finally:
            runtime_context_file.unlink(missing_ok=True)

    def _build_claude_options(
        self,
        route: AgentRoute,
        agent_output_dir: Path,
    ) -> ClaudeAgentOptionsT:
        effort = _normalize_effort(route.reasoning_effort)
        model_id = route.model or self.default_model_id

        def _stderr_callback(line: str) -> None:
            logger.error("Claude CLI stderr: %s", line)

        if _ClaudeAgentOptionsCls is None:
            raise RuntimeError("Claude Agent SDK is not installed yet. Run uv sync and retry.")

        return _ClaudeAgentOptionsCls(
            cwd=route.agent_dir,
            model=model_id,
            effort=effort,
            max_turns=self.max_turns,
            permission_mode="bypassPermissions",
            setting_sources=["project"],
            add_dirs=[self.outputs_root, agent_output_dir],
            allowed_tools=route.allowed_tools,
            disallowed_tools=route.disallowed_tools,
            env=dict(self.sdk_env),
            extra_args={"agent": route.agent_id},
            stderr=_stderr_callback,
        )

    def _build_payload(self, request: ExecutionRequest, agent_output_dir: Path) -> dict[str, Any]:
        payload = {
            "agent": {
                "agent_id": request.route.agent_id,
                "agent_output_dir": str(agent_output_dir),
                "route": {
                    "emoji": request.route.emoji,
                    "params": _normalize_json_value(request.route.params),
                    "model": request.route.model,
                    "reasoning_effort": request.route.reasoning_effort,
                    "allowed_tools": request.route.allowed_tools,
                    "disallowed_tools": request.route.disallowed_tools,
                },
            },
            "trigger": {
                "source": request.trigger.source,
                "emoji": request.trigger.emoji,
                "user_id": request.trigger.user_id,
                "observed_at": request.trigger.observed_at,
            },
            "triggers": [
                {
                    "source": trigger.source,
                    "emoji": trigger.emoji,
                    "user_id": trigger.user_id,
                    "observed_at": trigger.observed_at,
                }
                for trigger in request.triggers
            ],
            "queue": {
                "queue_target_id": request.queue_target_id,
                "attempt_count": request.queue_attempt_count,
                "merged_emojis": list(request.merged_emojis),
                "status": request.queue_status,
            },
            "message": _normalize_json_value(request.message_payload),
        }
        return payload

    def _build_prompt(self, payload: dict[str, Any], runtime_context_file: Path) -> str:
        prompt_payload = {
            **payload,
            "agent": {
                **payload["agent"],
                "runtime_context_file": str(runtime_context_file),
            },
        }
        rendered_payload = json.dumps(prompt_payload, ensure_ascii=False, indent=2, sort_keys=True)

        return "\n".join(
            [
                "A Discord trigger invoked the current Claude agent.",
                (
                    "Use your configured agent definition, project skills, "
                    "and project MCP setup to decide and execute the follow-up behavior."
                ),
                (
                    "The application now queues trigger events in SQLite and merges them "
                    "by message_id + agent_id before execution."
                ),
                (
                    "The full runtime JSON context is also available on disk at "
                    "agent.runtime_context_file. Use that file as the source of truth "
                    "when invoking deterministic scripts."
                ),
                (
                    "Write durable files under agent.agent_output_dir unless your route "
                    "explicitly says otherwise."
                ),
                "",
                "Discord event context (JSON):",
                rendered_payload,
            ]
        )


def _normalize_effort(value: str | None) -> ReasoningEffort | None:
    if value not in _VALID_EFFORTS:
        return None
    return cast(ReasoningEffort, value)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_value(item) for item in value]
    return value


def _write_runtime_context_file(agent_dir: Path, payload: dict[str, Any]) -> Path:
    runtime_dir = agent_dir / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="trigger-",
        suffix=".json",
        dir=runtime_dir,
        delete=False,
    ) as file:
        json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
        return Path(file.name)


def _snapshot_output_tree(base_dir: Path) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    if not base_dir.exists():
        return snapshot

    for path in sorted(p for p in base_dir.rglob("*") if p.is_file()):
        stat = path.stat()
        snapshot[path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _detect_output_changes(
    base_dir: Path,
    before_snapshot: dict[Path, tuple[int, int]],
) -> tuple[Path, ...]:
    changed: list[Path] = []
    if not base_dir.exists():
        return ()

    for path in sorted(p for p in base_dir.rglob("*") if p.is_file()):
        stat = path.stat()
        current = (stat.st_mtime_ns, stat.st_size)
        if before_snapshot.get(path) != current:
            changed.append(path)
    return tuple(changed)


async def _run_claude_query(prompt: str, options: ClaudeAgentOptionsT) -> str:
    if (
        _sdk_query is None
        or _AssistantMessageCls is None
        or _ResultMessageCls is None
        or _TextBlockCls is None
    ):
        raise RuntimeError("Claude Agent SDK is not installed yet. Run uv sync and retry.")

    assistant_fragments: list[str] = []
    final_result: str | None = None

    try:
        async for msg in _sdk_query(prompt=prompt, options=options):
            if isinstance(msg, _AssistantMessageCls):
                for block in msg.content:
                    if isinstance(block, _TextBlockCls) and block.text.strip():
                        assistant_fragments.append(block.text.strip())
            elif isinstance(msg, _ResultMessageCls) and isinstance(msg.result, str):
                if msg.result.strip():
                    final_result = msg.result.strip()
    except Exception:
        if final_result or assistant_fragments:
            logger.warning(
                "Claude query ended with non-zero exit after producing output; "
                "returning partial result",
                exc_info=True,
            )
        else:
            raise

    if final_result:
        return final_result
    if assistant_fragments:
        return "\n".join(assistant_fragments)
    return "Claude task completed."
