#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent_manifest import AgentRoute, load_agent_manifest
from src.config import Settings
from src.executor import AgentExecutor, ExecutionRequest, ExecutionTrigger

GITLAB_HELPER = (
    REPO_ROOT
    / "agents"
    / "issue-whisperer"
    / ".claude"
    / "skills"
    / "gitlab"
    / "scripts"
    / "gitlab_api.sh"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the issue-whisperer Claude agent against a synthetic Discord message. "
            "Prefer full GitLab issue URLs so the agent can resolve the project reliably."
        )
    )
    parser.add_argument(
        "--message",
        default="",
        help="Raw Discord message content to send to the agent.",
    )
    parser.add_argument(
        "--message-file",
        type=Path,
        help="Load Discord message content from a UTF-8 text file.",
    )
    parser.add_argument(
        "--issue-url",
        action="append",
        default=[],
        help="GitLab issue URL to include in the generated message. Repeatable.",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        help=(
            "Explicit GitLab project id used for the latest-issues workflow. "
            "Required when the script should fetch issues automatically."
        ),
    )
    parser.add_argument(
        "--latest-issues",
        type=int,
        default=3,
        help="How many latest issues to fetch when --project-id is used.",
    )
    parser.add_argument(
        "--message-id",
        type=int,
        default=int(datetime.now(UTC).timestamp() * 1000),
        help="Synthetic Discord message id. Defaults to the current UTC timestamp in ms.",
    )
    parser.add_argument(
        "--jump-url",
        default="",
        help="Optional Discord jump URL for the synthetic message.",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=REPO_ROOT / "outputs",
        help="Directory where durable agent outputs should be written.",
    )
    args = parser.parse_args()

    if args.message and args.message_file is not None:
        parser.error("Use either --message or --message-file, not both.")
    if args.latest_issues < 1:
        parser.error("--latest-issues must be at least 1.")

    if args.project_id is not None and (
        args.message or args.message_file is not None or args.issue_url
    ):
        parser.error(
            "--project-id cannot be combined with --message, --message-file, or --issue-url."
        )
    if (
        args.project_id is None
        and not args.message
        and args.message_file is None
        and not args.issue_url
    ):
        parser.error(
            "Provide --project-id, --message, --message-file, or at least one --issue-url."
        )

    return args


def load_message_content(args: argparse.Namespace) -> str:
    if args.message_file is not None:
        return args.message_file.read_text(encoding="utf-8").strip()
    if args.message:
        return args.message.strip()
    return "Please summarize these GitLab issues:\n" + "\n".join(args.issue_url)


def run_gitlab_helper(*helper_args: str) -> str:
    cmd = ["bash", str(GITLAB_HELPER), "--repo", str(REPO_ROOT), *helper_args]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or "(no stderr)"
        stdout = result.stdout.strip()
        details = stderr if stderr != "(no stderr)" else stdout or "(no output)"
        raise RuntimeError(f"GitLab helper failed for {' '.join(helper_args)}: {details}")
    return result.stdout.strip()


def gitlab_request_json(endpoint: str, *query_args: str) -> Any:
    body = run_gitlab_helper("request", "GET", endpoint, *query_args)
    return json.loads(body)


def load_project(project_id: int) -> dict[str, Any]:
    project = gitlab_request_json(f"/projects/{project_id}")
    if not isinstance(project, dict):
        raise RuntimeError(f"Unexpected GitLab project response for project id {project_id!r}.")
    return project


def load_latest_issue_urls(project_id: int, limit: int) -> tuple[dict[str, Any], list[str]]:
    project = load_project(project_id)
    project_id = project.get("id")
    if project_id is None:
        raise RuntimeError("GitLab project response did not include an id.")

    issues = gitlab_request_json(
        f"/projects/{project_id}/issues",
        "state=all",
        "order_by=created_at",
        "sort=desc",
        f"per_page={limit}",
    )
    if not isinstance(issues, list):
        raise RuntimeError(f"Unexpected GitLab issues response for project id {project_id!r}.")

    issue_urls = [str(item.get("web_url", "")).strip() for item in issues]
    issue_urls = [url for url in issue_urls if url]
    if not issue_urls:
        raise RuntimeError(f"No issues were returned for project id {project_id!r}.")

    return project, issue_urls


def build_project_message(project: dict[str, Any], issue_urls: list[str]) -> str:
    project_path = str(project.get("path_with_namespace", project.get("name", ""))).strip()
    return (
        f"Please summarize the latest {len(issue_urls)} GitLab issues from {project_path}:\n"
        + "\n".join(issue_urls)
    )


def resolve_manifest_path(settings: Settings) -> Path:
    manifest_path = settings.emoji_agent_manifest
    if manifest_path.is_absolute():
        return manifest_path
    return (REPO_ROOT / manifest_path).resolve()


def load_issue_whisperer_route(settings: Settings) -> AgentRoute:
    manifest = load_agent_manifest(resolve_manifest_path(settings))
    route = manifest.execution_route_for_agent("issue-whisperer")
    if route is None:
        raise RuntimeError("Could not find agent_id='issue-whisperer' in agents/agents.yaml.")
    return route


def build_message_payload(message_id: int, content: str, jump_url: str) -> dict[str, Any]:
    timestamp = datetime.now(UTC).isoformat()
    return {
        "id": message_id,
        "content": content,
        "clean_content": content,
        "system_content": "",
        "jump_url": jump_url,
        "created_at": timestamp,
        "edited_at": None,
        "pinned": False,
        "flags": 0,
        "author": {
            "id": 0,
            "name": "manual-tester",
            "display_name": "Manual Tester",
            "global_name": "Manual Tester",
            "bot": False,
        },
        "channel": {
            "id": 0,
            "name": "manual-test",
            "type": "text",
        },
        "guild": {
            "id": 0,
            "name": "local-test",
        },
        "attachments": [],
        "embeds": [],
        "mentions": [],
        "role_mentions": [],
        "channel_mentions": [],
        "stickers": [],
        "reactions": [],
        "reference": None,
    }


async def run_test(args: argparse.Namespace) -> int:
    settings = Settings(_env_file=REPO_ROOT / ".env")
    route = load_issue_whisperer_route(settings)

    selected_project: dict[str, Any] | None = None
    issue_urls: list[str] = []
    if args.project_id is not None:
        selected_project, issue_urls = load_latest_issue_urls(args.project_id, args.latest_issues)
        content = build_project_message(selected_project, issue_urls)
    else:
        content = load_message_content(args)

    jump_url = args.jump_url or (
        "https://discord.example.test/channels/local/manual/" + str(args.message_id)
    )
    message_payload = build_message_payload(args.message_id, content, jump_url)
    trigger = ExecutionTrigger(
        source="manual_test",
        emoji=route.emoji,
        user_id=None,
        observed_at=message_payload["created_at"],
    )

    executor = AgentExecutor(
        default_model_id=settings.claude_model,
        max_turns=settings.claude_max_turns,
        outputs_root=args.outputs_root.resolve(),
        sdk_env=settings.claude_sdk_env,
    )
    result = await executor.execute(
        ExecutionRequest(
            route=route,
            message_payload=message_payload,
            trigger=trigger,
            triggers=(trigger,),
            queue_target_id=args.message_id,
            queue_attempt_count=1,
            merged_emojis=(route.emoji,),
            queue_status="manual_test",
        )
    )

    print("issue-whisperer run completed")
    print(f"message_id: {args.message_id}")
    print(f"jump_url: {jump_url}")
    if selected_project is not None:
        print("project_id: " + str(selected_project.get("id", "")))
        print(
            "project: "
            + str(selected_project.get("path_with_namespace", selected_project.get("name", "")))
        )
    if issue_urls:
        print("issue_urls:")
        for url in issue_urls:
            print(f"  - {url}")
    print("changed_files:")
    for path in result.changed_output_files:
        print(f"  - {path}")
    print("agent_output:")
    print(result.agent_output)
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run_test(args))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
