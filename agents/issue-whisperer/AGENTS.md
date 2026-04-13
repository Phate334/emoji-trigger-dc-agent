# issue-whisperer Project Conventions

`agents/issue-whisperer/` is a standalone Claude Code project for GitLab issue summary triggers.

## Goal

- Trigger from `agents/agents.yaml` and summarize GitLab issues referenced in the Discord message.
- Write a durable Markdown summary file under `/app/outputs/issue-whisperer/` for each trigger.
- Keep issue access read-only via the GitLab REST helper script.

## Local Project Rules

- Keep issue-specific behavior inside this project instead of changing `src/`.
- Use `.claude/agents/issue-whisperer.md` as the filesystem-based Claude agent definition.
- Keep reusable API behavior in `.claude/skills/gitlab/`.
- Keep issue summarization in `.claude/skills/issue-summary/` and its script.
- Read runtime values from `agent.runtime_context_file` and write durable files under `agent.agent_output_dir`.
- Do not edit files outside the agent output directory.
- Do not call mutating GitLab endpoints; this agent is read-only.

## Expected Layout

- `AGENTS.md`: local project intent, constraints, and collaboration rules.
- `.claude/agents/issue-whisperer.md`: Claude agent definition.
- `.claude/skills/gitlab/`: copied GitLab read-only API skill for this agent.
- `.claude/skills/issue-summary/SKILL.md`: issue-summary invocation instructions.
- `.claude/skills/issue-summary/scripts/summarize_issue.py`: issue extraction and output writer.
