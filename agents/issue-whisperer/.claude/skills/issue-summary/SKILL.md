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
