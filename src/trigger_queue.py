from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .agent_manifest import AgentManifest, AgentRoute
from .executor import (
    AgentExecutor,
    ExecutionRequest,
    ExecutionResult,
    ExecutionTrigger,
    TriggerContext,
)

logger = logging.getLogger("emoji-trigger-agent")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_messages (
    message_id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    channel_name TEXT,
    channel_type TEXT,
    guild_id INTEGER,
    guild_name TEXT,
    author_id INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    author_display_name TEXT NOT NULL,
    message_created_at TEXT,
    message_snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'error', 'finished')),
    pending_emojis_json TEXT NOT NULL,
    processing_emojis_json TEXT NOT NULL,
    last_finished_emojis_json TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    claim_token TEXT,
    claim_expires_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (message_id, agent_id),
    FOREIGN KEY (message_id) REFERENCES queue_messages(message_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS queue_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    emoji TEXT NOT NULL,
    source TEXT NOT NULL,
    reactor_user_id INTEGER,
    observed_at TEXT NOT NULL,
    route_snapshot_json TEXT NOT NULL,
    message_snapshot_json TEXT NOT NULL,
    claim_token TEXT,
    claimed_at TEXT,
    processed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (target_id) REFERENCES queue_targets(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES queue_messages(message_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_queue_targets_status
    ON queue_targets(status, next_attempt_at, updated_at, id);

CREATE INDEX IF NOT EXISTS idx_queue_events_target
    ON queue_events(target_id, processed_at, claim_token, observed_at, id);
"""


@dataclass(slots=True, frozen=True)
class QueueTriggerEvent:
    id: int
    emoji: str
    source: str
    user_id: int | None
    observed_at: str


@dataclass(slots=True, frozen=True)
class QueuedExecutionItem:
    target_id: int
    message_id: int
    agent_id: str
    claim_token: str
    merged_emojis: tuple[str, ...]
    attempt_count: int
    status: str
    message_payload: dict[str, Any]
    trigger_events: tuple[QueueTriggerEvent, ...]


@dataclass(slots=True)
class QueueTargetState:
    target_id: int
    status: str
    pending_emojis: set[str]
    processing_emojis: set[str]
    last_finished_emojis: set[str]
    attempt_count: int
    next_attempt_at: str
    claim_token: str | None
    claim_expires_at: str | None
    last_error: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> QueueTargetState:
        return cls(
            target_id=int(row["id"]),
            status=str(row["status"]),
            pending_emojis=_load_emojis(row["pending_emojis_json"]),
            processing_emojis=_load_emojis(row["processing_emojis_json"]),
            last_finished_emojis=_load_emojis(row["last_finished_emojis_json"]),
            attempt_count=int(row["attempt_count"]),
            next_attempt_at=str(row["next_attempt_at"]),
            claim_token=str(row["claim_token"]) if row["claim_token"] is not None else None,
            claim_expires_at=(
                str(row["claim_expires_at"]) if row["claim_expires_at"] is not None else None
            ),
            last_error=str(row["last_error"]) if row["last_error"] is not None else None,
        )

    def has_seen(self, emoji: str) -> bool:
        return (
            emoji in self.pending_emojis
            or emoji in self.processing_emojis
            or emoji in self.last_finished_emojis
        )

    def reopen_for_trigger(self, emoji: str, now: str) -> None:
        self.pending_emojis.add(emoji)
        self.status = "pending"
        self.attempt_count = 0
        self.next_attempt_at = now
        self.last_error = None

    def register_trigger(self, emoji: str, now: str) -> str | None:
        if self.status == "finished":
            if emoji in self.last_finished_emojis:
                return now
            self.reopen_for_trigger(emoji, now)
            return None

        if self.status == "processing":
            if emoji in self.processing_emojis or emoji in self.last_finished_emojis:
                return now
            self.pending_emojis.add(emoji)
            return None

        if self.status == "pending":
            if emoji in self.last_finished_emojis and emoji not in self.pending_emojis:
                return now
            self.pending_emojis.add(emoji)
            return None

        if self.status == "error":
            if self.has_seen(emoji):
                return now
            self.reopen_for_trigger(emoji, now)
            return None

        raise ValueError(f"Unsupported queue target status: {self.status}")


class TriggerQueueStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    async def enqueue_trigger(
        self,
        route: AgentRoute,
        message_payload: dict[str, Any],
        trigger: TriggerContext,
    ) -> None:
        await asyncio.to_thread(self._enqueue_trigger_sync, route, message_payload, trigger)

    async def claim_next(self, *, claim_timeout_seconds: int) -> QueuedExecutionItem | None:
        return await asyncio.to_thread(self._claim_next_sync, claim_timeout_seconds)

    async def mark_success(self, item: QueuedExecutionItem) -> None:
        await asyncio.to_thread(self._mark_success_sync, item)

    async def mark_failure(
        self,
        item: QueuedExecutionItem,
        *,
        error_message: str,
        max_retries: int,
        retry_delay_seconds: int,
    ) -> None:
        await asyncio.to_thread(
            self._mark_failure_sync,
            item,
            error_message,
            max_retries,
            retry_delay_seconds,
        )

    async def recover_expired_claims(self) -> int:
        return await asyncio.to_thread(self._recover_expired_claims_sync)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        with closing(connection) as conn:
            yield conn

    def _enqueue_trigger_sync(
        self,
        route: AgentRoute,
        message_payload: dict[str, Any],
        trigger: TriggerContext,
    ) -> None:
        now = _utcnow()
        message_id = _require_int(message_payload.get("id"), key="message.id")

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _upsert_message(conn, message_payload, now)

            row = conn.execute(
                """
                SELECT *
                FROM queue_targets
                WHERE message_id = ? AND agent_id = ?
                """,
                (message_id, route.agent_id),
            ).fetchone()

            event_processed_at: str | None = None
            if row is None:
                conn.execute(
                    """
                    INSERT INTO queue_targets (
                        message_id,
                        agent_id,
                        status,
                        pending_emojis_json,
                        processing_emojis_json,
                        last_finished_emojis_json,
                        attempt_count,
                        next_attempt_at,
                        claim_token,
                        claim_expires_at,
                        last_error,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, 'pending', ?, '[]', '[]', 0, ?, NULL, NULL, NULL, ?, ?)
                    """,
                    (
                        message_id,
                        route.agent_id,
                        _dump_json([trigger.emoji]),
                        now,
                        now,
                        now,
                    ),
                )
                target_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                state = QueueTargetState.from_row(row)
                target_id = state.target_id
                event_processed_at = state.register_trigger(trigger.emoji, now)

                conn.execute(
                    """
                    UPDATE queue_targets
                    SET status = ?,
                        pending_emojis_json = ?,
                        processing_emojis_json = ?,
                        last_finished_emojis_json = ?,
                        attempt_count = ?,
                        next_attempt_at = ?,
                        claim_token = ?,
                        claim_expires_at = ?,
                        last_error = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        state.status,
                        _dump_json(state.pending_emojis),
                        _dump_json(state.processing_emojis),
                        _dump_json(state.last_finished_emojis),
                        state.attempt_count,
                        state.next_attempt_at,
                        state.claim_token,
                        state.claim_expires_at,
                        state.last_error,
                        now,
                        target_id,
                    ),
                )

            conn.execute(
                """
                INSERT INTO queue_events (
                    target_id,
                    message_id,
                    agent_id,
                    emoji,
                    source,
                    reactor_user_id,
                    observed_at,
                    route_snapshot_json,
                    message_snapshot_json,
                    claim_token,
                    claimed_at,
                    processed_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    target_id,
                    message_id,
                    route.agent_id,
                    route.emoji,
                    trigger.source,
                    trigger.user_id,
                    trigger.observed_at or now,
                    _dump_json(_route_snapshot(route)),
                    _dump_json(message_payload),
                    event_processed_at,
                    now,
                ),
            )
            conn.commit()

    def _claim_next_sync(self, claim_timeout_seconds: int) -> QueuedExecutionItem | None:
        now = _utcnow()
        claim_expires_at = _utcnow(offset_seconds=claim_timeout_seconds)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT t.*, m.message_snapshot_json
                FROM queue_targets AS t
                INNER JOIN queue_messages AS m ON m.message_id = t.message_id
                WHERE t.status = 'pending'
                  AND t.next_attempt_at <= ?
                  AND t.pending_emojis_json != '[]'
                ORDER BY t.updated_at ASC, t.id ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None

            merged_emojis = tuple(sorted(_load_emojis(row["pending_emojis_json"])))
            if not merged_emojis:
                conn.commit()
                return None

            claim_token = uuid.uuid4().hex
            conn.execute(
                """
                UPDATE queue_targets
                SET status = 'processing',
                    processing_emojis_json = ?,
                    pending_emojis_json = '[]',
                    claim_token = ?,
                    claim_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    _dump_json(merged_emojis),
                    claim_token,
                    claim_expires_at,
                    now,
                    int(row["id"]),
                ),
            )

            placeholders = ", ".join("?" for _ in merged_emojis)
            conn.execute(
                f"""
                UPDATE queue_events
                SET claim_token = ?, claimed_at = ?
                WHERE target_id = ?
                  AND processed_at IS NULL
                  AND claim_token IS NULL
                  AND emoji IN ({placeholders})
                """,
                (claim_token, now, int(row["id"]), *merged_emojis),
            )
            claimed_events = conn.execute(
                """
                SELECT id, emoji, source, reactor_user_id, observed_at
                FROM queue_events
                WHERE target_id = ? AND claim_token = ?
                ORDER BY observed_at ASC, id ASC
                """,
                (int(row["id"]), claim_token),
            ).fetchall()
            conn.commit()

        trigger_events = tuple(
            QueueTriggerEvent(
                id=int(event["id"]),
                emoji=str(event["emoji"]),
                source=str(event["source"]),
                user_id=(
                    int(event["reactor_user_id"]) if event["reactor_user_id"] is not None else None
                ),
                observed_at=str(event["observed_at"]),
            )
            for event in claimed_events
        )
        return QueuedExecutionItem(
            target_id=int(row["id"]),
            message_id=int(row["message_id"]),
            agent_id=str(row["agent_id"]),
            claim_token=claim_token,
            merged_emojis=merged_emojis,
            attempt_count=int(row["attempt_count"]) + 1,
            status="processing",
            message_payload=json.loads(str(row["message_snapshot_json"])),
            trigger_events=trigger_events,
        )

    def _mark_success_sync(self, item: QueuedExecutionItem) -> None:
        now = _utcnow()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT *
                FROM queue_targets
                WHERE id = ? AND claim_token = ? AND status = 'processing'
                """,
                (item.target_id, item.claim_token),
            ).fetchone()
            if row is None:
                conn.commit()
                return

            pending_emojis = _load_emojis(row["pending_emojis_json"])
            processing_emojis = _load_emojis(row["processing_emojis_json"])
            next_status = "pending" if pending_emojis else "finished"

            conn.execute(
                """
                UPDATE queue_targets
                SET status = ?,
                    pending_emojis_json = ?,
                    processing_emojis_json = '[]',
                    last_finished_emojis_json = ?,
                    next_attempt_at = ?,
                    claim_token = NULL,
                    claim_expires_at = NULL,
                    last_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    _dump_json(pending_emojis),
                    _dump_json(processing_emojis),
                    now if next_status == "pending" else str(row["next_attempt_at"]),
                    now,
                    item.target_id,
                ),
            )
            conn.execute(
                """
                UPDATE queue_events
                SET processed_at = ?
                WHERE claim_token = ?
                """,
                (now, item.claim_token),
            )
            conn.commit()

    def _mark_failure_sync(
        self,
        item: QueuedExecutionItem,
        error_message: str,
        max_retries: int,
        retry_delay_seconds: int,
    ) -> None:
        now = _utcnow()
        next_attempt_at = _utcnow(offset_seconds=retry_delay_seconds)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT *
                FROM queue_targets
                WHERE id = ? AND claim_token = ? AND status = 'processing'
                """,
                (item.target_id, item.claim_token),
            ).fetchone()
            if row is None:
                conn.commit()
                return

            pending_emojis = _load_emojis(row["pending_emojis_json"])
            processing_emojis = _load_emojis(row["processing_emojis_json"])
            pending_emojis.update(processing_emojis)
            failure_count = int(row["attempt_count"]) + 1
            next_status = "pending" if failure_count <= max_retries else "error"

            conn.execute(
                """
                UPDATE queue_targets
                SET status = ?,
                    pending_emojis_json = ?,
                    processing_emojis_json = '[]',
                    attempt_count = ?,
                    next_attempt_at = ?,
                    claim_token = NULL,
                    claim_expires_at = NULL,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    next_status,
                    _dump_json(pending_emojis),
                    failure_count,
                    next_attempt_at if next_status == "pending" else now,
                    error_message,
                    now,
                    item.target_id,
                ),
            )
            conn.execute(
                """
                UPDATE queue_events
                SET claim_token = NULL, claimed_at = NULL
                WHERE claim_token = ? AND processed_at IS NULL
                """,
                (item.claim_token,),
            )
            conn.commit()

    def _recover_expired_claims_sync(self) -> int:
        now = _utcnow()

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT *
                FROM queue_targets
                WHERE status = 'processing'
                  AND claim_expires_at IS NOT NULL
                  AND claim_expires_at < ?
                """,
                (now,),
            ).fetchall()
            recovered = 0
            for row in rows:
                pending_emojis = _load_emojis(row["pending_emojis_json"])
                processing_emojis = _load_emojis(row["processing_emojis_json"])
                pending_emojis.update(processing_emojis)
                conn.execute(
                    """
                    UPDATE queue_targets
                    SET status = 'pending',
                        pending_emojis_json = ?,
                        processing_emojis_json = '[]',
                        next_attempt_at = ?,
                        claim_token = NULL,
                        claim_expires_at = NULL,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        _dump_json(pending_emojis),
                        now,
                        now,
                        int(row["id"]),
                    ),
                )
                if row["claim_token"] is not None:
                    conn.execute(
                        """
                        UPDATE queue_events
                        SET claim_token = NULL, claimed_at = NULL
                        WHERE claim_token = ? AND processed_at IS NULL
                        """,
                        (str(row["claim_token"]),),
                    )
                recovered += 1
            conn.commit()
            return recovered


class TriggerQueueWorker:
    def __init__(
        self,
        store: TriggerQueueStore,
        manifest: AgentManifest,
        executor: AgentExecutor,
        *,
        poll_interval_seconds: float,
        concurrency: int,
        claim_timeout_seconds: int,
        retry_count: int,
        retry_delay_seconds: int,
    ) -> None:
        self.store = store
        self.manifest = manifest
        self.executor = executor
        self.poll_interval_seconds = poll_interval_seconds
        self.concurrency = concurrency
        self.claim_timeout_seconds = claim_timeout_seconds
        self.retry_count = retry_count
        self.retry_delay_seconds = retry_delay_seconds
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._tasks:
            return

        recovered = await self.store.recover_expired_claims()
        if recovered:
            logger.warning("Recovered %s expired queue claim(s)", recovered)

        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._run_loop(worker_id), name=f"trigger-queue-worker-{worker_id}")
            for worker_id in range(self.concurrency)
        ]

    async def stop(self) -> None:
        if not self._tasks:
            return

        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        results = await asyncio.gather(*self._tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.error("Queue worker stopped with error: %s", result)
        self._tasks = []

    async def _run_loop(self, worker_id: int) -> None:
        while not self._stop_event.is_set():
            item = await self.store.claim_next(claim_timeout_seconds=self.claim_timeout_seconds)
            if item is None:
                await asyncio.sleep(self.poll_interval_seconds)
                continue

            await self._execute_item(worker_id, item)

    async def _execute_item(self, worker_id: int, item: QueuedExecutionItem) -> None:
        logger.info(
            (
                "Processing queued trigger: worker=%s target_id=%s message_id=%s "
                "agent_id=%s emojis=%s attempt=%s"
            ),
            worker_id,
            item.target_id,
            item.message_id,
            item.agent_id,
            ", ".join(item.merged_emojis),
            item.attempt_count,
        )

        try:
            request = self._build_execution_request(item)
            result = await self.executor.execute(request)
        except Exception as exc:
            logger.exception(
                "Queued trigger failed: target_id=%s message_id=%s agent_id=%s",
                item.target_id,
                item.message_id,
                item.agent_id,
            )
            await self.store.mark_failure(
                item,
                error_message=str(exc),
                max_retries=self.retry_count,
                retry_delay_seconds=self.retry_delay_seconds,
            )
            return

        await self.store.mark_success(item)
        _log_execution_result(item, result)
        logger.info(
            "Queued trigger finished: target_id=%s message_id=%s agent_id=%s emojis=%s",
            item.target_id,
            item.message_id,
            item.agent_id,
            ", ".join(item.merged_emojis),
        )

    def _build_execution_request(self, item: QueuedExecutionItem) -> ExecutionRequest:
        route = self.manifest.execution_route_for_agent(item.agent_id)
        if route is None:
            raise RuntimeError(f"No manifest route found for agent_id={item.agent_id}")
        if not item.trigger_events:
            raise RuntimeError(
                f"Queue target {item.target_id} for agent {item.agent_id} has no trigger events"
            )

        primary_trigger = item.trigger_events[0]
        runtime_route = _runtime_route(route, primary_trigger.emoji)
        triggers = tuple(
            ExecutionTrigger(
                source=event.source,
                emoji=event.emoji,
                user_id=event.user_id,
                observed_at=event.observed_at,
            )
            for event in item.trigger_events
        )
        return ExecutionRequest(
            route=runtime_route,
            message_payload=item.message_payload,
            trigger=triggers[0],
            triggers=triggers,
            queue_target_id=item.target_id,
            queue_attempt_count=item.attempt_count,
            merged_emojis=item.merged_emojis,
            queue_status=item.status,
        )


def _upsert_message(
    conn: sqlite3.Connection,
    message_payload: dict[str, Any],
    observed_at: str,
) -> None:
    author = message_payload.get("author") or {}
    channel = message_payload.get("channel") or {}
    guild = message_payload.get("guild") or {}
    conn.execute(
        """
        INSERT INTO queue_messages (
            message_id,
            channel_id,
            channel_name,
            channel_type,
            guild_id,
            guild_name,
            author_id,
            author_name,
            author_display_name,
            message_created_at,
            message_snapshot_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            channel_name = excluded.channel_name,
            channel_type = excluded.channel_type,
            guild_id = excluded.guild_id,
            guild_name = excluded.guild_name,
            author_id = excluded.author_id,
            author_name = excluded.author_name,
            author_display_name = excluded.author_display_name,
            message_created_at = excluded.message_created_at,
            message_snapshot_json = excluded.message_snapshot_json,
            updated_at = excluded.updated_at
        """,
        (
            _require_int(message_payload.get("id"), key="message.id"),
            _require_int(channel.get("id"), key="message.channel.id"),
            channel.get("name"),
            channel.get("type"),
            guild.get("id"),
            guild.get("name"),
            _require_int(author.get("id"), key="message.author.id"),
            _require_str(author.get("name"), key="message.author.name"),
            _require_str(author.get("display_name"), key="message.author.display_name"),
            message_payload.get("created_at"),
            _dump_json(message_payload),
            observed_at,
            observed_at,
        ),
    )


def _route_snapshot(route: AgentRoute) -> dict[str, Any]:
    return {
        "emoji": route.emoji,
        "agent_id": route.agent_id,
        "params": route.params,
        "model": route.model,
        "reasoning_effort": route.reasoning_effort,
    }


def _runtime_route(route: AgentRoute, emoji: str) -> AgentRoute:
    return AgentRoute(
        emoji=emoji,
        agent_id=route.agent_id,
        agent_dir=route.agent_dir,
        agent_file=route.agent_file,
        params=dict(route.params),
        model=route.model,
        reasoning_effort=route.reasoning_effort,
    )


def _log_execution_result(item: QueuedExecutionItem, result: ExecutionResult) -> None:
    if result.agent_output.strip():
        logger.debug("Agent output suppressed from channel: %s", result.agent_output)
    logger.debug(
        "Verified agent output files for target %s: %s",
        item.target_id,
        ", ".join(str(path) for path in result.changed_output_files),
    )


def _dump_json(value: Any) -> str:
    if isinstance(value, set):
        value = sorted(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load_emojis(raw: str) -> set[str]:
    values = json.loads(raw)
    if not isinstance(values, list):
        raise ValueError(f"Expected list JSON for emoji set, got: {raw}")
    return {str(value) for value in values}


def _utcnow(*, offset_seconds: int = 0) -> str:
    return (datetime.now(UTC) + timedelta(seconds=offset_seconds)).isoformat()


def _require_int(value: Any, *, key: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"Expected integer value for {key}")
    return value


def _require_str(value: Any, *, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected non-empty string value for {key}")
    return value
