---
description: Append one markdown memo entry for a Discord trigger by calling the bundled write script.
allowed-tools: Bash(python3 *)
---

# memo-write

Append one memo entry to a per-channel markdown file under the runtime-provided output directory.

## Contract
- Read values from the runtime JSON payload in the prompt.
- Call the bundled script instead of generating Python code inline.
- For `memo-agent`, run the script directly via `Bash` instead of the `Skill` tool.
- The output file path is decided at runtime as `<agent_output_dir>/<channel_id>.md`.

## Command

Run this command with the real values from the runtime prompt:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/write_channel_memo.py" \
  --output-dir "ACTUAL_AGENT_OUTPUT_DIR" \
  --channel-id "ACTUAL_CHANNEL_ID" \
  --channel-name "ACTUAL_CHANNEL_NAME" \
  --guild-name "ACTUAL_GUILD_NAME" \
  --emoji "ACTUAL_TRIGGER_EMOJI" \
  --trigger-source "ACTUAL_TRIGGER_SOURCE" \
  --trigger-user-id "ACTUAL_TRIGGER_USER_ID" \
  --message-id "ACTUAL_MESSAGE_ID" \
  --author-name "ACTUAL_AUTHOR_NAME" \
  --author-id "ACTUAL_AUTHOR_ID" \
  --created-at "ACTUAL_CREATED_AT" \
  --edited-at "ACTUAL_EDITED_AT" \
  --jump-url "ACTUAL_JUMP_URL" \
  --content "ACTUAL_MESSAGE_CONTENT"
```

## Notes
- Use the actual runtime values; never keep the placeholders above.
- If `trigger.user_id`, `guild.name`, `edited_at`, or `channel.name` are missing, pass an empty string.
- `content` may be empty; still write an entry.
- The bundled script also accepts `--message-content` as an alias for `--content`.
- `CLAUDE_SKILL_DIR` resolves to this skill's directory, so the script path does not need to be hardcoded in agent prompts.
- The script creates the output directory and file as needed.
