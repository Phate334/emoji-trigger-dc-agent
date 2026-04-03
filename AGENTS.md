# Project Runtime Conventions

- Runtime routing config must be loaded from `agents/agents.yaml`.
- Runtime agent roots must live under `agents/<agent-id>/`.
- Each runtime agent must use its own Claude project directory at `agents/<agent-id>/.claude/`.
- Filesystem-based Claude agent definitions must live under `agents/<agent-id>/.claude/agents/<agent-id>.md`.
- Skill assets for a runtime agent must live under `agents/<agent-id>/.claude/skills/<skill-id>/SKILL.md`.
- Agent-specific MCP config must follow Claude Code conventions, for example `agents/<agent-id>/.mcp.json`.
- Avoid hardcoded emoji routes inside application code.
- Keep route behavior declarative in the manifest and isolate execution logic in `src/executor.py`.
