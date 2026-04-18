from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Settings

_LOG_RECORD_DEFAULT_KEYS = frozenset(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    """Render application logs as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        subsystem = _derive_subsystem(record)
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "subsystem": subsystem,
            "message": record.getMessage(),
        }

        extras = {
            key: _normalize_value(value)
            for key, value in record.__dict__.items()
            if key not in _LOG_RECORD_DEFAULT_KEYS and not key.startswith("_")
        }
        payload.update(extras)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def log_extra(event: str, /, **fields: object) -> dict[str, object]:
    """Build structured log metadata for standard logger calls."""
    extra: dict[str, object] = {"event": event}
    extra.update({key: value for key, value in fields.items() if value is not None})
    return extra


def setup_logging(settings: Settings) -> None:
    """Configure logging for the application."""
    log_level_name = settings.log_level.upper()
    discord_log_level_name = settings.discord_log_level_name.upper()

    log_level = getattr(logging, log_level_name, logging.INFO)
    discord_log_level = getattr(logging, discord_log_level_name, log_level)

    handler = logging.StreamHandler(stream=sys.stdout)
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )

    logging.basicConfig(level=log_level, handlers=[handler], force=True)
    logging.captureWarnings(True)
    logging.getLogger("discord").setLevel(discord_log_level)


def _normalize_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _derive_subsystem(record: logging.LogRecord) -> str:
    if record.name.startswith("discord"):
        return "discord_py"
    if record.name.startswith("emoji-trigger-agent.claude"):
        return "claude_sdk"
    return "app"
