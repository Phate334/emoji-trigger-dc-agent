---
name: gitlab
description: Use this skill when the user needs read-only data from GitLab through the REST API, especially for self-hosted or Community Edition projects. Trigger it for GitLab issue search, issue comments or discussions, merge request or PR status, unresolved review threads, branch file contents, pipelines, jobs, CI logs, and similar repository inspection tasks. It uses curl or wget, discovers GITLAB_TOKEN from the repo .env first, and expects callers to pass an explicit project id or project ref for project-scoped reads.
compatibility: Requires bash, git, and curl or wget. Works best when the caller already knows the target GitLab host and project identifier.
---

# GitLab Read-Only API Skill

Use this skill for read-only GitLab REST API work against GitLab Free or Community Edition compatible endpoints.

## Discovery Order

Always resolve connection details in this order:

1. Find the repo root with `git rev-parse --show-toplevel`.
2. Read `GITLAB_TOKEN` from `<repo>/.env` first.
3. If `GITLAB_TOKEN` is not in `.env`, fall back to the exported environment variable.
4. Prefer an explicit project id or project ref supplied by the caller.
5. Resolve `GITLAB_HOST` from `<repo>/.env`, exported environment variables, or repository context when available.

The bundled helper already follows this sequence. Use it instead of rebuilding the discovery logic each time.

## Always Do This

- Start from the repo root before calling the helper.
- For project-scoped reads, pass an explicit project id or project ref instead of relying on repository remotes.
- Treat GitLab PR as GitLab merge request. Use merge request endpoints for PR requests.
- Stay read-only. Use `GET` or `HEAD` only.
- Prefer the helper at `.claude/skills/gitlab/scripts/gitlab_api.sh` over hand-written `curl` unless you need a one-off edge case.
- Add narrow filters such as `search`, `state`, `ref`, `per_page`, or `scope` so responses stay small.
- Prefer Discussions API when the user cares about thread resolution, unresolved comments, or review state.
- Prefer Notes API when the user wants a flat chronological comment stream or issue activity.
- Prefer the repository raw file endpoint when the user wants file contents.
- For CI investigation, fetch pipelines first, then jobs, then the failing job trace.
- Summarize the important fields for the user instead of dumping raw JSON unless they explicitly ask for it.

## Quick Start

```bash
repo_root="$(git rev-parse --show-toplevel)"
helper="$repo_root/.claude/skills/gitlab/scripts/gitlab_api.sh"

"$helper" --repo "$repo_root" discover
project_ref="$($helper --repo "$repo_root" project-ref "group/project")"
```

Search issues in a specific project:

```bash
"$helper" --repo "$repo_root" request GET \
	"/projects/$project_ref/issues" \
	"scope=all" \
	"search=pipeline timeout" \
	"per_page=5"
```

Get a merge request plus review thread state:

```bash
mr_iid="42"

"$helper" --repo "$repo_root" request GET \
	"/projects/$project_ref/merge_requests/$mr_iid"

"$helper" --repo "$repo_root" request GET \
	"/projects/$project_ref/merge_requests/$mr_iid/discussions"
```

Read a file from a branch:

```bash
file_ref="$($helper urlencode ".gitlab-ci.yml")"

"$helper" --repo "$repo_root" request GET \
	"/projects/$project_ref/repository/files/$file_ref/raw" \
	"ref=main"
```

Inspect the latest failed pipeline on a branch and fetch the job log:

```bash
branch="main"

"$helper" --repo "$repo_root" request GET \
	"/projects/$project_ref/pipelines" \
	"ref=$branch" \
	"status=failed" \
	"per_page=1"

pipeline_id="<from previous response>"

"$helper" --repo "$repo_root" request GET \
	"/projects/$project_ref/pipelines/$pipeline_id/jobs"

job_id="<failed job id>"

"$helper" --repo "$repo_root" request GET \
	"/projects/$project_ref/jobs/$job_id/trace"
```

## Supported Read Workflows

- Search issues in an explicitly selected project or fetch a specific issue.
- Read issue notes or issue discussions.
- Search merge requests or fetch a specific merge request.
- Inspect merge request discussions, notes, reviewers, commits, and pipelines.
- Read a file from a specific branch, tag, or commit.
- Inspect pipelines, pipeline jobs, job details, and job traces.

## Response Interpretation

- Merge request status: start with `state`, `detailed_merge_status`, `draft`, `merge_error`, `blocking_discussions_resolved`, and `head_pipeline.status`.
- Discussion state: in merge request discussions, use `resolvable`, `resolved`, `resolved_by`, and `resolved_at`.
- Pipeline state: use `status`, `detailed_status`, `ref`, `sha`, `web_url`, `started_at`, and `finished_at`.
- Job failures: use `status`, `stage`, `name`, `failure_reason`, and then fetch `/trace` for the log.
- Issue conversations: use Discussions API for thread structure and Notes API for flat comment history.

## When To Read The Reference

Read `.claude/skills/gitlab/references/read-apis.md` when you need:

- the exact endpoint for a supported read workflow
- guidance on when to choose notes versus discussions
- the best field set to summarize for issues, merge requests, pipelines, or jobs
- concrete examples for issue search, MR review state, branch file reads, or pipeline log inspection

## Output Guidance

- If the user asks a question, answer it directly after fetching the minimum useful set of endpoints.
- Include identifiers the user can reuse, such as issue IID, MR IID, pipeline ID, job ID, branch, ref, and `web_url` when relevant.
- If a log or file is large, inspect only the relevant portion and summarize the key lines.
- If discovery fails because the token, host, or explicit project identifier is missing, say exactly which input is missing and what was checked.
