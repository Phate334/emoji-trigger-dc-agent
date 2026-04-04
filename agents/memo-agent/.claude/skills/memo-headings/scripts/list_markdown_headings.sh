#!/usr/bin/env bash
set -euo pipefail

file_path="${1:-}"

if [[ -z "${file_path}" || ! -f "${file_path}" ]]; then
  exit 0
fi

LC_ALL=C awk '
/^#{1,6}[[:space:]]+/ {
  line = $0
  level = 0
  while (substr(line, level + 1, 1) == "#") {
    level++
  }
  heading = substr(line, level + 2)
  sub(/[[:space:]]+$/, "", heading)
  printf "%s\t%s\t%s\n", level, NR, heading
}
' "${file_path}"
