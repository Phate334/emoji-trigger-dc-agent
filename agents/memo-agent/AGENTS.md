# memo-agent Project Conventions

`agents/memo-agent/` is a standalone Claude Code project for Discord memo triggers.

## Goal

- Consume the runtime JSON context prepared by `src/`.
- Append one markdown memo entry per successful trigger into `/app/outputs/memo-agent/<channel-id>.md`.

## Local Project Rules

- Keep memo-specific behavior inside this project instead of moving it into `src/`.
- Use `.claude/agents/memo-agent.md` as the filesystem-based Claude agent definition for this project.
- Keep reusable write instructions in `.claude/skills/memo-write/SKILL.md`.
- Keep deterministic helper code in `.claude/skills/memo-write/scripts/`.
- Do not generate ad hoc scripts at runtime for file-writing behavior.
- Read output paths from the runtime payload rather than hardcoding channel-specific destinations.

## Expected Layout

- `AGENTS.md`: local project intent, constraints, and collaboration rules
- `.claude/agents/memo-agent.md`: Claude agent definition
- `.claude/skills/memo-write/SKILL.md`: memo write procedure
- `.claude/skills/memo-write/scripts/write_channel_memo.py`: deterministic file-writing implementation
