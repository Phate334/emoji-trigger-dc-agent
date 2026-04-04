---
description: Upsert one readable memo topic section for a Discord trigger by calling the bundled write script.
allowed-tools: Bash(python3 *)
---

# memo-write

Upsert one `##` topic section into a per-channel markdown file under the runtime-provided output directory.

## Contract
- Read values from the runtime context JSON file at `agent.runtime_context_file`.
- Use the script's current CLI surface only: `--event-json` is required and `--section-title` is optional.
- Decide the target section title only after checking the current heading index.
- If the target section already exists, preserve the existing chapter body and add the new Discord note into that section.
- Call the bundled script instead of generating Python code inline.
- For `memo-agent`, run the script directly via `Bash` instead of the `Skill` tool.
- The script decides the output file path at runtime as a filesystem-safe `<channel name>.md`, with fallback handling if an existing file for a different channel already uses that name.

## Command

Run this command with the real runtime values:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/write_channel_memo.py" \
  --event-json "ACTUAL_RUNTIME_CONTEXT_FILE" \
  --section-title "SECTION TITLE"
```

## Notes
- The runtime context file already contains the full Discord message payload and output directory.
- `content` may be empty; the script still writes a readable section.
- `CLAUDE_SKILL_DIR` resolves to this skill's directory, so the script path does not need to be hardcoded in agent prompts.
- The script creates the output directory and file as needed.
- The document H1 should be the channel name, and each memo topic should stay as its own `##` section.
- Do not use legacy per-field flags such as `--output-dir` or `--channel-id`; those values now come only from the runtime JSON payload.
- Reuse the exact existing `##` heading text when you are updating an existing section.
- The note content should keep the author and the original message text instead of compressing them into a high-level summary.
