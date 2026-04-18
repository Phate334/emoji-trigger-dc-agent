from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any, Literal, cast

from .agent_manifest import AgentRoute
from .logging_config import log_extra

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
_HookMatcherCls = getattr(_claude_agent_sdk, "HookMatcher", None)
_RateLimitEventCls = getattr(_claude_agent_sdk, "RateLimitEvent", None)
_ResultMessageCls = getattr(_claude_agent_sdk, "ResultMessage", None)
_SystemMessageCls = getattr(_claude_agent_sdk, "SystemMessage", None)
_TaskNotificationMessageCls = getattr(_claude_agent_sdk, "TaskNotificationMessage", None)
_TaskProgressMessageCls = getattr(_claude_agent_sdk, "TaskProgressMessage", None)
_TaskStartedMessageCls = getattr(_claude_agent_sdk, "TaskStartedMessage", None)
_ThinkingBlockCls = getattr(_claude_agent_sdk, "ThinkingBlock", None)
_TextBlockCls = getattr(_claude_agent_sdk, "TextBlock", None)
_ToolResultBlockCls = getattr(_claude_agent_sdk, "ToolResultBlock", None)
_ToolUseBlockCls = getattr(_claude_agent_sdk, "ToolUseBlock", None)
_sdk_query = getattr(_claude_agent_sdk, "query", None)


type ReasoningEffort = Literal["low", "medium", "high", "max"]

_VALID_EFFORTS = frozenset({"low", "medium", "high", "max"})
_CLAUDE_HOOK_EVENTS = (
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Notification",
    "PermissionRequest",
    "SubagentStart",
    "SubagentStop",
)
_MAX_LOG_TEXT_CHARS = 240
_MAX_LOG_LIST_ITEMS = 8

logger = logging.getLogger(__name__)
claude_logger = logging.getLogger("emoji-trigger-agent.claude")


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
            options = self._build_claude_options(request, agent_output_dir)
            agent_output = await _run_claude_query(prompt, options, request=request)
            changed_output_files = _detect_output_changes(agent_output_dir, before_snapshot)
            if not changed_output_files:
                if agent_output.strip():
                    logger.error(
                        "Claude agent returned without file changes",
                        extra=log_extra(
                            "executor.no_output_files",
                            agent_id=route.agent_id,
                            queue_target_id=request.queue_target_id,
                            message_id=request.message_payload.get("id"),
                            agent_output_chars=len(agent_output),
                            output_dir=agent_output_dir,
                        ),
                    )
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
        request: ExecutionRequest,
        agent_output_dir: Path,
    ) -> ClaudeAgentOptionsT:
        route = request.route
        effort = _normalize_effort(route.reasoning_effort)
        model_id = route.model or self.default_model_id

        def _stderr_callback(line: str) -> None:
            claude_logger.warning(
                "Claude CLI emitted stderr output",
                extra=_claude_log_extra(
                    "executor.claude_stderr",
                    request,
                    stderr_line=_truncate_text(line),
                ),
            )

        async def _hook_callback(
            hook_input: Any,
            tool_use_id: str | None,
            _context: Any,
        ) -> dict[str, Any]:
            _log_claude_hook_event(request, hook_input, tool_use_id=tool_use_id)
            return {}

        if _ClaudeAgentOptionsCls is None:
            raise RuntimeError("Claude Agent SDK is not installed yet. Run uv sync and retry.")

        hooks = _build_claude_hooks(_hook_callback)

        return _ClaudeAgentOptionsCls(
            cwd=route.agent_dir,
            model=model_id,
            effort=effort,
            max_turns=self.max_turns,
            permission_mode="bypassPermissions",
            setting_sources=["project"],
            add_dirs=[self.outputs_root, agent_output_dir],
            env=dict(self.sdk_env),
            extra_args={"agent": route.agent_id},
            stderr=_stderr_callback,
            hooks=hooks,
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


async def _run_claude_query(
    prompt: str,
    options: ClaudeAgentOptionsT,
    *,
    request: ExecutionRequest,
) -> str:
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
            if _TaskStartedMessageCls is not None and isinstance(msg, _TaskStartedMessageCls):
                claude_logger.info(
                    "Claude task started",
                    extra=_claude_log_extra(
                        "executor.claude_task_started",
                        request,
                        task_id=msg.task_id,
                        session_id=msg.session_id,
                        tool_use_id=msg.tool_use_id,
                        task_type=msg.task_type,
                        description=_truncate_text(msg.description),
                    ),
                )
            elif _TaskProgressMessageCls is not None and isinstance(msg, _TaskProgressMessageCls):
                claude_logger.info(
                    "Claude task progress",
                    extra=_claude_log_extra(
                        "executor.claude_task_progress",
                        request,
                        task_id=msg.task_id,
                        session_id=msg.session_id,
                        tool_use_id=msg.tool_use_id,
                        description=_truncate_text(msg.description),
                        last_tool_name=msg.last_tool_name,
                        usage=msg.usage,
                    ),
                )
            elif _TaskNotificationMessageCls is not None and isinstance(
                msg, _TaskNotificationMessageCls
            ):
                task_notification_logger = (
                    claude_logger.warning if msg.status != "completed" else claude_logger.info
                )
                task_notification_logger(
                    "Claude task notification",
                    extra=_claude_log_extra(
                        "executor.claude_task_notification",
                        request,
                        task_id=msg.task_id,
                        session_id=msg.session_id,
                        tool_use_id=msg.tool_use_id,
                        task_status=msg.status,
                        output_file=msg.output_file,
                        summary=_truncate_text(msg.summary),
                        usage=msg.usage,
                    ),
                )
            elif isinstance(msg, _AssistantMessageCls):
                for block in msg.content:
                    if isinstance(block, _TextBlockCls) and block.text.strip():
                        assistant_fragments.append(block.text.strip())
                claude_logger.debug(
                    "Claude assistant message",
                    extra=_claude_log_extra(
                        "executor.claude_assistant_message",
                        request,
                        **_summarize_assistant_message(msg),
                    ),
                )
            elif _RateLimitEventCls is not None and isinstance(msg, _RateLimitEventCls):
                rate_limit_logger = _rate_limit_logger(msg)
                rate_limit_logger(
                    "Claude rate limit event",
                    extra=_claude_log_extra(
                        "executor.claude_rate_limit",
                        request,
                        session_id=msg.session_id,
                        rate_limit_info=_summarize_rate_limit_info(msg.rate_limit_info),
                    ),
                )
            elif isinstance(msg, _ResultMessageCls) and isinstance(msg.result, str):
                if msg.result.strip():
                    final_result = msg.result.strip()
                result_logger = claude_logger.error if msg.is_error else claude_logger.info
                result_logger(
                    "Claude result received",
                    extra=_claude_log_extra(
                        "executor.claude_result",
                        request,
                        session_id=msg.session_id,
                        duration_ms=msg.duration_ms,
                        duration_api_ms=msg.duration_api_ms,
                        is_error=msg.is_error,
                        num_turns=msg.num_turns,
                        stop_reason=msg.stop_reason,
                        total_cost_usd=msg.total_cost_usd,
                        usage=msg.usage,
                        model_usage=msg.model_usage,
                        permission_denial_count=len(msg.permission_denials or []),
                        errors=msg.errors,
                        result_chars=len(msg.result or ""),
                    ),
                )
            elif _SystemMessageCls is not None and isinstance(msg, _SystemMessageCls):
                claude_logger.debug(
                    "Claude system message",
                    extra=_claude_log_extra(
                        "executor.claude_system_message",
                        request,
                        subtype=getattr(msg, "subtype", None),
                        data_summary=_summarize_value(getattr(msg, "data", {})),
                    ),
                )
    except Exception:
        if final_result or assistant_fragments:
            claude_logger.warning(
                "Claude query ended with non-zero exit after producing output; "
                "returning partial result",
                extra=_claude_log_extra(
                    "executor.partial_result",
                    request,
                    assistant_fragment_count=len(assistant_fragments),
                    final_result_chars=len(final_result or ""),
                ),
                exc_info=True,
            )
        else:
            raise

    if final_result:
        return final_result
    if assistant_fragments:
        return "\n".join(assistant_fragments)
    return "Claude task completed."


def _build_claude_hooks(callback: Any) -> dict[str, list[Any]] | None:
    if _HookMatcherCls is None:
        return None
    return {event: [_HookMatcherCls(hooks=[callback])] for event in _CLAUDE_HOOK_EVENTS}


def _claude_log_extra(
    event: str,
    request: ExecutionRequest,
    /,
    **fields: object,
) -> dict[str, object]:
    request_fields = {
        "agent_id": request.route.agent_id,
        "queue_target_id": request.queue_target_id,
        "queue_attempt_count": request.queue_attempt_count,
        "message_id": request.message_payload.get("id"),
        "channel_id": _nested_mapping_value(request.message_payload, "channel", "id"),
        "guild_id": _nested_mapping_value(request.message_payload, "guild", "id"),
    }
    request_fields.update({key: value for key, value in fields.items() if value is not None})
    return log_extra(event, **request_fields)


def _nested_mapping_value(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _truncate_text(value: str, limit: int = _MAX_LOG_TEXT_CHARS) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 15]}... (truncated)"


def _summarize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_text(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        mapping_summary: dict[str, Any] = {}
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            if index >= _MAX_LOG_LIST_ITEMS:
                mapping_summary["_truncated_keys"] = len(items) - _MAX_LOG_LIST_ITEMS
                break
            mapping_summary[str(key)] = _summarize_value(item)
        return mapping_summary
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        sequence_summary = [_summarize_value(item) for item in items[:_MAX_LOG_LIST_ITEMS]]
        if len(items) > _MAX_LOG_LIST_ITEMS:
            sequence_summary.append(f"... ({len(items) - _MAX_LOG_LIST_ITEMS} more items)")
        return sequence_summary
    return str(value)


def _summarize_assistant_message(message: Any) -> dict[str, object]:
    tool_names: list[str] = []
    tool_use_ids: list[str] = []
    text_block_count = 0
    text_chars = 0
    thinking_block_count = 0
    thinking_chars = 0
    tool_result_count = 0
    tool_result_error_count = 0

    for block in message.content:
        if _TextBlockCls is not None and isinstance(block, _TextBlockCls):
            text_block_count += 1
            text_chars += len(block.text)
            continue
        if _ThinkingBlockCls is not None and isinstance(block, _ThinkingBlockCls):
            thinking_block_count += 1
            thinking_chars += len(block.thinking)
            continue
        if _ToolUseBlockCls is not None and isinstance(block, _ToolUseBlockCls):
            tool_names.append(block.name)
            tool_use_ids.append(block.id)
            continue
        if _ToolResultBlockCls is not None and isinstance(block, _ToolResultBlockCls):
            tool_result_count += 1
            if block.is_error:
                tool_result_error_count += 1

    return {
        "assistant_message_id": getattr(message, "message_id", None),
        "session_id": getattr(message, "session_id", None),
        "model": getattr(message, "model", None),
        "stop_reason": getattr(message, "stop_reason", None),
        "assistant_error": getattr(message, "error", None),
        "usage": getattr(message, "usage", None),
        "text_block_count": text_block_count,
        "text_chars": text_chars,
        "thinking_block_count": thinking_block_count,
        "thinking_chars": thinking_chars,
        "tool_use_count": len(tool_names),
        "tool_names": tool_names,
        "tool_use_ids": tool_use_ids,
        "tool_result_count": tool_result_count,
        "tool_result_error_count": tool_result_error_count,
    }


def _summarize_rate_limit_info(rate_limit_info: Any) -> dict[str, Any]:
    return {
        "status": getattr(rate_limit_info, "status", None),
        "rate_limit_type": getattr(rate_limit_info, "rate_limit_type", None),
        "utilization": getattr(rate_limit_info, "utilization", None),
        "resets_at": getattr(rate_limit_info, "resets_at", None),
        "overage_status": getattr(rate_limit_info, "overage_status", None),
        "overage_resets_at": getattr(rate_limit_info, "overage_resets_at", None),
        "overage_disabled_reason": getattr(rate_limit_info, "overage_disabled_reason", None),
    }


def _rate_limit_logger(rate_limit_event: Any) -> Any:
    status = getattr(rate_limit_event.rate_limit_info, "status", None)
    if status == "rejected":
        return claude_logger.error
    if status == "allowed_warning":
        return claude_logger.warning
    return claude_logger.info


def _log_claude_hook_event(
    request: ExecutionRequest,
    hook_input: Any,
    *,
    tool_use_id: str | None,
) -> None:
    if not isinstance(hook_input, Mapping):
        claude_logger.debug(
            "Claude hook callback emitted unexpected payload",
            extra=_claude_log_extra(
                "executor.claude_hook_unknown",
                request,
                hook_payload=str(hook_input),
            ),
        )
        return

    hook_event_name = hook_input.get("hook_event_name")
    common_fields = {
        "session_id": hook_input.get("session_id"),
        "tool_use_id": tool_use_id or hook_input.get("tool_use_id"),
        "subagent_id": hook_input.get("agent_id"),
        "subagent_type": hook_input.get("agent_type"),
    }

    if hook_event_name == "PreToolUse":
        claude_logger.info(
            "Claude tool starting",
            extra=_claude_log_extra(
                "executor.claude_hook_pre_tool_use",
                request,
                **common_fields,
                tool_name=hook_input.get("tool_name"),
                tool_input_summary=_summarize_value(hook_input.get("tool_input")),
            ),
        )
        return

    if hook_event_name == "PostToolUse":
        claude_logger.info(
            "Claude tool completed",
            extra=_claude_log_extra(
                "executor.claude_hook_post_tool_use",
                request,
                **common_fields,
                tool_name=hook_input.get("tool_name"),
                tool_input_summary=_summarize_value(hook_input.get("tool_input")),
                tool_response_summary=_summarize_value(hook_input.get("tool_response")),
            ),
        )
        return

    if hook_event_name == "PostToolUseFailure":
        claude_logger.warning(
            "Claude tool failed",
            extra=_claude_log_extra(
                "executor.claude_hook_post_tool_use_failure",
                request,
                **common_fields,
                tool_name=hook_input.get("tool_name"),
                tool_input_summary=_summarize_value(hook_input.get("tool_input")),
                error=_truncate_text(str(hook_input.get("error", ""))),
                is_interrupt=hook_input.get("is_interrupt"),
            ),
        )
        return

    if hook_event_name == "PermissionRequest":
        claude_logger.info(
            "Claude permission request",
            extra=_claude_log_extra(
                "executor.claude_hook_permission_request",
                request,
                **common_fields,
                tool_name=hook_input.get("tool_name"),
                tool_input_summary=_summarize_value(hook_input.get("tool_input")),
                permission_suggestion_count=len(hook_input.get("permission_suggestions", [])),
            ),
        )
        return

    if hook_event_name == "Notification":
        claude_logger.info(
            "Claude notification received",
            extra=_claude_log_extra(
                "executor.claude_hook_notification",
                request,
                **common_fields,
                notification_type=hook_input.get("notification_type"),
                title=_truncate_text(str(hook_input.get("title", ""))),
                message=_truncate_text(str(hook_input.get("message", ""))),
            ),
        )
        return

    if hook_event_name == "SubagentStart":
        claude_logger.info(
            "Claude subagent started",
            extra=_claude_log_extra(
                "executor.claude_hook_subagent_start",
                request,
                **common_fields,
                subagent_id=hook_input.get("agent_id"),
                subagent_type=hook_input.get("agent_type"),
            ),
        )
        return

    if hook_event_name == "SubagentStop":
        claude_logger.info(
            "Claude subagent stopped",
            extra=_claude_log_extra(
                "executor.claude_hook_subagent_stop",
                request,
                **common_fields,
                subagent_id=hook_input.get("agent_id"),
                subagent_type=hook_input.get("agent_type"),
                agent_transcript_path=hook_input.get("agent_transcript_path"),
                stop_hook_active=hook_input.get("stop_hook_active"),
            ),
        )
        return

    claude_logger.debug(
        "Claude hook event",
        extra=_claude_log_extra(
            "executor.claude_hook_generic",
            request,
            **common_fields,
            hook_event_name=hook_event_name,
            hook_input_summary=_summarize_value(hook_input),
        ),
    )
