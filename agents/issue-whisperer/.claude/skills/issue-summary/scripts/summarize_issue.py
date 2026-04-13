#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-json", required=True, help="Path to runtime context json")
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def find_repo_root(start: Path) -> Path:
    for candidate in start.parents:
        if (candidate / ".git").exists():
            return candidate
    if start.is_file():
        start = start.parent
    if (start / ".git").exists():
        return start
    git_dir = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if git_dir.returncode == 0 and git_dir.stdout.strip():
        return Path(git_dir.stdout.strip())
    return start


def run_helper(helper: Path, repo_root: Path, *args: str) -> str:
    cmd = ["bash", str(helper), "--repo", str(repo_root), *args]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def extract_issue_iids(message_text: str) -> list[str]:
    issue_urls = re.findall(r"https?://[^\s]+/-/issues/(\d+)", message_text)
    issue_mentions = re.findall(r"(?<![\w/])#(\d+)\b", message_text)
    combined = issue_urls + issue_mentions
    seen: set[str] = set()
    ordered: list[str] = []
    for issue in combined:
        if issue in seen:
            continue
        seen.add(issue)
        ordered.append(issue)
    return ordered


def summarize_issue(
    issue_iid: str, helper: Path, repo_root: Path, project_ref: str
) -> dict[str, Any] | None:
    if not project_ref:
        return None
    endpoint = f"/projects/{project_ref}/issues/{issue_iid}"
    body = run_helper(helper, repo_root, "request", "GET", endpoint)
    return json.loads(body)


def render_markdown(
    message: dict[str, Any], trigger: dict[str, Any], summaries: list[dict[str, Any]], issue_count: int
) -> str:
    lines: list[str] = [
        "# GitLab Issue Summary",
        "",
        "- Source message: " + str(message.get("jump_url", "")),
        "- Message id: " + str(message.get("id", "")),
        "- Trigger emoji: " + str(trigger.get("emoji", "")),
        "- Trigger source: " + str(trigger.get("source", "")),
        "- Triggered at: " + str(trigger.get("observed_at", "")),
        "- Issue count: " + str(issue_count),
        "- Updated: " + datetime.utcnow().isoformat() + "Z",
        "",
    ]

    if not summaries:
        lines.extend(
            [
                "No issue reference found in message content.",
                "",
                "Tip: include either `https://gitlab.example.com/.../-/issues/<iid>` or `#<iid>` in the message.",
            ]
        )
        return "\n".join(lines)

    for item in summaries:
        lines.append(f"## Issue #{item.get('iid')}")
        lines.append(f"- Title: {item.get('title')}")
        lines.append(f"- State: {item.get('state')}")
        labels = item.get("labels") or []
        lines.append("- Labels: " + (", ".join(labels) if isinstance(labels, list) else str(labels)))
        lines.append(f"- Assignees: " + ", ".join(a.get("name", "") for a in item.get("assignees", [])))
        lines.append(f"- Author: {item.get('author', {}).get('name', '')}")
        lines.append(f"- Web: {item.get('web_url')}")
        lines.append(f"- Updated at: {item.get('updated_at')}")
        lines.append(f"- User notes: {item.get('user_notes_count')}")
        lines.append("")
        description = item.get("description") or "(No description)"
        lines.append(description)
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    payload = load_payload(Path(args.event_json))

    message = payload.get("message", {}) if isinstance(payload.get("message"), dict) else {}
    trigger = payload.get("trigger", {}) if isinstance(payload.get("trigger"), dict) else {}
    content = str(message.get("content", ""))
    agent_output_dir = Path(payload["agent"]["agent_output_dir"])
    message_id = message.get("id", "unknown")

    issue_iids = extract_issue_iids(content)

    skill_dir = Path(__file__).resolve().parent.parent.parent
    helper = skill_dir / "gitlab" / "scripts" / "gitlab_api.sh"
    repo_root = find_repo_root(Path(__file__).resolve())

    summaries: list[dict[str, Any]] = []
    project_ref = ""
    if issue_iids:
        project_ref = run_helper(helper, repo_root, "project-ref")
        for issue_iid in issue_iids:
            try:
                issue = summarize_issue(issue_iid, helper, repo_root, project_ref)
                if issue is not None:
                    summaries.append(issue)
            except subprocess.CalledProcessError as exc:
                summaries.append(
                    {
                        "iid": issue_iid,
                        "title": "Unable to fetch issue",
                        "state": "error",
                        "labels": [],
                        "assignees": [],
                        "author": {"name": ""},
                        "web_url": "",
                        "updated_at": "",
                        "user_notes_count": "",
                        "description": exc.stderr or str(exc),
                    }
                )

    markdown = render_markdown(message, trigger, summaries, len(issue_iids))
    output_file = agent_output_dir / f"issue-summary-{message_id}.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(markdown + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
