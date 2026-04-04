---
description: List markdown headings from a memo file with simple bash text processing tools.
allowed-tools: Bash(bash *)
---

# memo-headings

List markdown headings from a target memo file before choosing where new memo content belongs.

## Command

```bash
bash "${CLAUDE_SKILL_DIR}/scripts/list_markdown_headings.sh" "ABSOLUTE_TARGET_FILE"
```

## Output format

Each line is tab-separated:

```text
<level>\t<line_number>\t<heading text>
```

## Notes
- Treat `##` headings as the candidate topic sections for memo placement.
- A missing or empty file returns no output and is not an error.
- Use this before deciding whether to reuse an existing section title or create a new one.
