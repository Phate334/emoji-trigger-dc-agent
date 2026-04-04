# memo-agent Project Conventions

`agents/memo-agent/` is a standalone Claude Code project for Discord memo triggers.

## Goal

- Consume the runtime JSON context prepared by `src/`.
- Organize each successful trigger into a readable markdown memo document at `/app/outputs/memo-agent/<channel-name>.md`.
- Group related notes into topic sections so new memo content can be merged into an existing `##` section instead of only appending a raw log entry.
- Preserve the author's name and the original message text inside the matching markdown chapter rather than replacing them with an over-compressed summary.
- Keep the markdown structure readable: H1 is the channel name, and each topic is a `##` section.

## Local Project Rules

- Keep memo-specific behavior inside this project instead of moving it into `src/`.
- Use `.claude/agents/memo-agent.md` as the filesystem-based Claude agent definition for this project.
- Keep reusable write instructions in `.claude/skills/memo-write/SKILL.md`.
- Keep reusable heading-index instructions in `.claude/skills/memo-headings/SKILL.md`.
- Keep deterministic helper code in `.claude/skills/memo-write/scripts/`.
- Keep simple shell helpers in each skill's `scripts/` directory rather than writing ad hoc shell pipelines during runtime.
- Do not generate ad hoc scripts at runtime for file-writing behavior.
- Read output paths from the runtime payload rather than hardcoding channel-specific destinations.
- Treat the runtime JSON file plus the bundled scripts as the only supported execution path; do not preserve legacy flag-by-flag write commands.
- Decide the target section only after inspecting the existing markdown heading index.
- If a section already exists, keep the existing chapter body and append the new Discord note into that chapter.
- Do not fetch or summarize hyperlink destination content; only organize the Discord message itself.

## Expected Layout

- `AGENTS.md`: local project intent, constraints, and collaboration rules
- `.claude/agents/memo-agent.md`: Claude agent definition
- `.claude/skills/memo-write/SKILL.md`: memo section upsert procedure
- `.claude/skills/memo-write/scripts/write_channel_memo.py`: deterministic file-writing implementation
- `.claude/skills/memo-headings/SKILL.md`: markdown heading index procedure
- `.claude/skills/memo-headings/scripts/list_markdown_headings.sh`: simple heading extraction helper
