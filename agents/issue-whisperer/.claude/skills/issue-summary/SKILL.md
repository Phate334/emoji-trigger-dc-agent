---
name: issue-summary
description: Parse issue references from a trigger context and write a durable GitLab issue summary file.
allowed-tools: Bash(python3 *)
---

# issue-summary

Run the bundled writer with the runtime context JSON path:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/summarize_issue.py" --event-json "ACTUAL_RUNTIME_CONTEXT_FILE"
```

Prefer fully qualified GitLab issue URLs in the runtime message. Do not rely on repository remotes to infer the target project.

If the agent needs a specific default project for shorthand `#<iid>` references, pass `--project-ref` explicitly:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/summarize_issue.py" \
  --event-json "ACTUAL_RUNTIME_CONTEXT_FILE" \
  --project-ref "group%2Fproject"
```
