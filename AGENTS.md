# Project Runtime Conventions

- Runtime routing config must be loaded from `codex/agents/agents.yaml`.
- Sub-agent instructions must live under `codex/agents/<agent-id>/AGENTS.md`.
- Skill assets must live under `codex/skills/<skill-id>/SKILL.md`.
- MCP profiles must live under `codex/mcp/<profile-id>.toml`.
- Avoid hardcoded emoji routes inside application code.
- Keep route behavior declarative in the manifest and isolate execution logic in `src/executor.py`.
