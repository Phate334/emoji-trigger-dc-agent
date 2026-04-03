# memo-write

Append one memo line to a TSV file safely in the container.

## Contract
- Input fields: `author`, `content`, `output_file`
- Output: exactly one appended line in format:
  `timestamp\tauthor\tcontent`

## Recommended Command
Use Python for consistent escaping and UTF-8 behavior:

```bash
python3 - <<'PY'
from datetime import datetime, UTC
from pathlib import Path

output_file = Path("/app/claude/runtime/memo.txt")
author = "<author>"
content = "<content>"

line = f"{datetime.now(UTC).isoformat()}\t{author}\t{content.replace(chr(10), ' ').strip()}"
output_file.parent.mkdir(parents=True, exist_ok=True)
with output_file.open("a", encoding="utf-8") as f:
    f.write(line + "\n")
PY
```

## Notes
- Replace `/app/claude/runtime/memo.txt` with route `params.output_file` value when present.
- Keep operation append-only.
- One trigger writes one line.
