# Project Runtime Conventions

## Directory Ownership

- `src/` owns the deterministic application runtime.
- `src/` is responsible for Discord event intake, manifest loading, config/env parsing, de-duplication, Claude invocation, runtime guardrails, and output verification.
- `agents/` owns declarative Claude behavior.
- `agents/agents.yaml` is the only runtime emoji routing manifest.
- `agents/<agent-id>/` contains one runtime Claude project per agent.
- `agents/<agent-id>/AGENTS.md` contains that agent project's local goals, constraints, and Claude Code working conventions.
- `agents/<agent-id>/.claude/agents/<agent-id>.md` is the filesystem-based Claude agent definition.
- `agents/<agent-id>/.claude/skills/<skill-id>/SKILL.md` contains skill instructions for that agent.
- `agents/<agent-id>/.claude/skills/<skill-id>/scripts/` contains pre-written scripts or other supporting files used by that skill.
- `agents/<agent-id>/.mcp.json` is the optional Claude Code MCP config for that agent only.
- `outputs/` is the durable runtime output root mounted into the container as `/app/outputs`.
- `outputs/<agent-id>/` is agent-owned output space for durable files produced by that agent.

## Boundary Rules

- Put shared platform logic in `src/`.
- Put agent-specific behavior in `agents/`.
- Do not hardcode emoji routes or agent-specific business rules in `src/`.
- Keep route behavior declarative in `agents/agents.yaml`.
- Keep Claude execution orchestration generic in `src/executor.py`; it must not know about individual agent behaviors such as `memo-agent`.
- If a change can be expressed by editing an agent prompt, skill, script, or route config, prefer changing `agents/` instead of `src/`.
- If a change affects every agent uniformly, implement it in `src/`.
- Each `agents/<agent-id>/` directory should follow Claude Code single-project conventions rather than behaving like an arbitrary asset folder.
- Each agent project should keep its own `AGENTS.md` with the agent's purpose, success criteria, important constraints, and how its local skills are arranged.
- Each agent project should organize reusable Claude Code assets under its own `.claude/` directory so the agent can run as an isolated project.
- Agents should consume the runtime JSON context prepared by `src/` and decide their own follow-up behavior from that input.
- Agents should execute pre-written scripts from their skill directories for side-effecting work rather than generating ad hoc scripts at runtime.
- Unless explicitly documented otherwise, agents should write durable artifacts under `/app/outputs/<agent-id>/`.

## Runtime Expectations

- `src/bot.py` decides when a trigger is eligible to be enqueued and writes trigger intake into the SQLite queue.
- `src/trigger_queue.py` merges work by `message_id + agent_id`, runs background workers, and manages `pending`, `processing`, `error`, and `finished` target states.
- `src/executor.py` passes the queued Discord message context to the selected agent and verifies that the agent actually changed files under its output directory before the run is treated as successful.
- A completed trigger should leave a durable file change under `outputs/<agent-id>/`.
- A completed trigger target should emit a log record describing the successful queued processing result.
- Queue state is durable in `/app/outputs/trigger_queue.sqlite3`; restarting the bot should recover expired in-flight claims back to `pending`.
