# Project Goals

- Run emoji-triggered Claude workflows for Discord messages.
- Keep routing declarative so new behaviors can be added without changing shared runtime code.
- Preserve a clear boundary between deterministic platform runtime and configurable agent behavior.
- Produce durable outputs for completed work.
- Recover safely from restarts and retry unfinished queued work.

## Architecture Principles

- `src/` owns the shared runtime.
- `agents/` owns declarative Claude behavior and routing configuration.
- `outputs/` stores durable runtime artifacts and is mounted at `/app/outputs`.
- `agents/agents.yaml` is the only runtime emoji routing manifest.
- Shared runtime code must stay generic and must not encode agent-specific business rules.
- Prefer changing prompts, skills, scripts, or route config in `agents/` before changing shared runtime logic in `src/`.
- If a change applies to every workflow uniformly, implement it in `src/`.

## Runtime Responsibilities

- `src/bot.py` accepts eligible Discord triggers and writes them into the SQLite-backed queue.
- `src/trigger_queue.py` merges work by `message_id + agent_id`, runs background workers, and manages queue state transitions.
- `src/executor.py` loads the queued Discord context, invokes the selected Claude workflow, and verifies that the run produced a durable output change.

## System Contract

- A completed trigger must leave a durable file change under `outputs/`.
- A completed trigger must emit a log record describing the successful queued processing result.
- Queue state is stored in `/app/outputs/trigger_queue.sqlite3`.
- After restart, expired in-flight claims must be returned to `pending`.
