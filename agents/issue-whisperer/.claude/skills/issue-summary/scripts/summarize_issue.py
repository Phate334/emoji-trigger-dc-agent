#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote


@dataclass(frozen=True, slots=True)
class IssueReference:
    iid: str
    project_path: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-json", required=True, help="Path to runtime context json")
    parser.add_argument(
        "--project-ref",
        default="",
        help="Optional default project ref for shorthand #<iid> references",
    )
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


def extract_issue_references(message_text: str) -> list[IssueReference]:
    matches: list[tuple[int, IssueReference]] = []

    for match in re.finditer(
        r"https?://[^\s/]+/(?P<project_path>.+?)/-/issues/(?P<iid>\d+)\b",
        message_text,
    ):
        matches.append(
            (
                match.start(),
                IssueReference(
                    iid=match.group("iid"),
                    project_path=unquote(match.group("project_path")).strip("/"),
                ),
            )
        )

    for match in re.finditer(r"(?<![\w/])#(?P<iid>\d+)\b", message_text):
        matches.append((match.start(), IssueReference(iid=match.group("iid"))))

    matches.sort(key=lambda item: item[0])
    return [reference for _, reference in matches]


def resolve_reference_project_ref(
    reference: IssueReference,
    default_project_ref: str,
    helper: Path,
    repo_root: Path,
    project_ref_cache: dict[str, str],
) -> str:
    if reference.project_path is None:
        if default_project_ref:
            return default_project_ref
        raise ValueError(f"No default project ref available for issue #{reference.iid}.")

    cached_project_ref = project_ref_cache.get(reference.project_path)
    if cached_project_ref is not None:
        return cached_project_ref

    project_ref = run_helper(helper, repo_root, "project-ref", reference.project_path)
    project_ref_cache[reference.project_path] = project_ref
    return project_ref


def summarize_issue(
    issue_iid: str, helper: Path, repo_root: Path, project_ref: str
) -> dict[str, Any] | None:
    if not project_ref:
        return None
    endpoint = f"/projects/{project_ref}/issues/{issue_iid}"
    body = run_helper(helper, repo_root, "request", "GET", endpoint)
    return json.loads(body)


def render_markdown(
    message: dict[str, Any],
    trigger: dict[str, Any],
    summaries: list[dict[str, Any]],
    issue_count: int,
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
        if item.get("_project_ref"):
            lines.append(f"- Project: {item.get('_project_ref')}")
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

    references = extract_issue_references(content)

    skill_dir = Path(__file__).resolve().parent.parent.parent
    helper = skill_dir / "gitlab" / "scripts" / "gitlab_api.sh"
    repo_root = find_repo_root(Path(__file__).resolve())

    summaries: list[dict[str, Any]] = []
    project_ref_cache: dict[str, str] = {}
    default_project_ref = args.project_ref.strip()
    default_project_error = ""
    if references and not default_project_ref:
        try:
            default_project_ref = run_helper(helper, repo_root, "project-ref")
        except subprocess.CalledProcessError as exc:
            default_project_error = exc.stderr.strip() or str(exc)

    seen_targets: set[tuple[str, str]] = set()
    if references:
        for reference in references:
            try:
                project_ref = resolve_reference_project_ref(
                    reference,
                    default_project_ref,
                    helper,
                    repo_root,
                    project_ref_cache,
                )
                target_key = (project_ref, reference.iid)
                if target_key in seen_targets:
                    continue
                seen_targets.add(target_key)

                issue = summarize_issue(reference.iid, helper, repo_root, project_ref)
                if issue is not None:
                    issue["_project_ref"] = project_ref
                    summaries.append(issue)
            except ValueError as exc:
                summaries.append(
                    {
                        "iid": reference.iid,
                        "_project_ref": default_project_ref,
                        "title": "Unable to resolve project",
                        "state": "error",
                        "labels": [],
                        "assignees": [],
                        "author": {"name": ""},
                        "web_url": "",
                        "updated_at": "",
                        "user_notes_count": "",
                        "description": default_project_error or str(exc),
                    }
                )
            except subprocess.CalledProcessError as exc:
                summaries.append(
                    {
                        "iid": reference.iid,
                        "_project_ref": reference.project_path or default_project_ref,
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

    markdown = render_markdown(message, trigger, summaries, len(summaries))
    output_file = agent_output_dir / f"issue-summary-{message_id}.md"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(markdown + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
