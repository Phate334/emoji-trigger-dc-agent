---
description: Append one markdown memo entry for a Discord trigger by calling the bundled write script.
allowed-tools: Bash(python3 *)
---

# memo-write

Append one memo entry to a per-channel markdown file under the runtime-provided output directory.

## Contract
- Read values from the runtime context JSON file at `agent.runtime_context_file`.
- Call the bundled script instead of generating Python code inline.
- For `memo-agent`, run the script directly via `Bash` instead of the `Skill` tool.
- The script decides the output file path at runtime as `<agent_output_dir>/<channel_id>.md`.

## Command

Run this command with the real runtime context file path:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/write_channel_memo.py" \
  --event-json "ACTUAL_RUNTIME_CONTEXT_FILE"
```

## Notes
- The runtime context file already contains the full Discord message payload and output directory.
- `content` may be empty; the script still writes an entry.
- `CLAUDE_SKILL_DIR` resolves to this skill's directory, so the script path does not need to be hardcoded in agent prompts.
- The script creates the output directory and file as needed.
- For runtime safety, this agent's route should allow only the bundled `python3 .claude/skills/memo-write/scripts/write_channel_memo.py --event-json ...` Bash prefix.
