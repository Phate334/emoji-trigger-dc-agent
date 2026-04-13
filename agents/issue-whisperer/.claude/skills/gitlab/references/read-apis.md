# GitLab Read APIs Reference

This reference captures the first supported set of GitLab Free or Community Edition read-only REST endpoints for this skill.

Official sources reviewed for this skill:

- [GitLab Issues API](https://docs.gitlab.com/api/issues/)
- [GitLab Notes API](https://docs.gitlab.com/api/notes/)
- [GitLab Discussions API](https://docs.gitlab.com/api/discussions/)
- [GitLab Merge Requests API](https://docs.gitlab.com/api/merge_requests/)
- [GitLab Repository Files API](https://docs.gitlab.com/api/repository_files/)
- [GitLab Pipelines API](https://docs.gitlab.com/api/pipelines/)
- [GitLab Jobs API](https://docs.gitlab.com/api/jobs/)

## Helper Recap

```bash
repo_root="$(git rev-parse --show-toplevel)"
helper="$repo_root/.claude/skills/gitlab/scripts/gitlab_api.sh"
project_ref="$($helper --repo "$repo_root" project-ref)"
```

Useful helper commands:

- `"$helper" --repo "$repo_root" discover`
- `"$helper" --repo "$repo_root" project-path`
- `"$helper" --repo "$repo_root" project-ref`
- `"$helper" urlencode "path/to/file"`
- `"$helper" --repo "$repo_root" request GET "/projects/$project_ref/..." "key=value" ...`

## Issues

### Search project issues

Use when the user asks to find matching issues in the current project.

Endpoint:

- `GET /projects/:id/issues`

Useful filters from GitLab Free:

- `scope=all`
- `search=<text>`
- `in=title,description`
- `state=opened|closed|all`
- `labels=a,b`
- `author_username=<user>`
- `assignee_username=<user>`
- `per_page=<n>`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/issues" \
  "scope=all" \
  "search=timeout" \
  "state=opened" \
  "per_page=10"
```

Key fields to summarize:

- `iid`
- `title`
- `state`
- `labels`
- `assignees`
- `updated_at`
- `web_url`

### Search group issues

Use when the user wants cross-project issue search within a group.

Endpoint:

- `GET /groups/:id/issues`

Example:

```bash
group_ref="$($helper urlencode "my-group")"

"$helper" --repo "$repo_root" request GET \
  "/groups/$group_ref/issues" \
  "scope=all" \
  "search=runner" \
  "per_page=10"
```

### Get one issue

Use when the user already has an issue IID.

Endpoint:

- `GET /projects/:id/issues/:issue_iid`

Example:

```bash
issue_iid="123"

"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/issues/$issue_iid"
```

Important fields:

- `title`
- `description`
- `state`
- `references`
- `assignees`
- `milestone`
- `user_notes_count`
- `_links.notes`
- `web_url`

### Issue notes versus issue discussions

Use Notes API when the user wants a flat stream of comments or system activity.

Endpoints:

- `GET /projects/:id/issues/:issue_iid/notes`
- `GET /projects/:id/issues/:issue_iid/notes/:note_id`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/issues/$issue_iid/notes" \
  "activity_filter=only_comments" \
  "sort=asc"
```

Use Discussions API when the user wants thread structure.

Endpoints:

- `GET /projects/:id/issues/:issue_iid/discussions`
- `GET /projects/:id/issues/:issue_iid/discussions/:discussion_id`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/issues/$issue_iid/discussions"
```

Important discussion fields:

- discussion `id`
- `individual_note`
- each note's `body`
- `author`
- `system`
- `created_at`

## Merge Requests

Treat PR requests as GitLab merge requests.

### Search project merge requests

Endpoint:

- `GET /projects/:id/merge_requests`

Useful filters from GitLab Free:

- `scope=all`
- `search=<text>`
- `in=title,description`
- `state=opened|merged|closed|all`
- `author_username=<user>`
- `reviewer_username=<user>`
- `labels=a,b`
- `per_page=<n>`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/merge_requests" \
  "scope=all" \
  "search=release" \
  "state=opened" \
  "per_page=10"
```

### Get one merge request

Endpoint:

- `GET /projects/:id/merge_requests/:merge_request_iid`

Example:

```bash
mr_iid="42"

"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/merge_requests/$mr_iid"
```

Important fields:

- `title`
- `description`
- `state`
- `draft`
- `detailed_merge_status`
- `blocking_discussions_resolved`
- `has_conflicts`
- `reviewers`
- `labels`
- `references`
- `web_url`
- `head_pipeline`

### Merge request discussions

Use this when the user cares about thread resolution or review state.

Endpoints:

- `GET /projects/:id/merge_requests/:merge_request_iid/discussions`
- `GET /projects/:id/merge_requests/:merge_request_iid/discussions/:discussion_id`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/merge_requests/$mr_iid/discussions"
```

Important fields:

- discussion `id`
- `individual_note`
- note `type`
- note `body`
- `resolvable`
- `resolved`
- `resolved_by`
- `resolved_at`
- `position` for diff notes

If the user asks whether review threads are still blocking the MR, combine:

- MR `blocking_discussions_resolved`
- discussion note `resolved` and `resolvable`

### Merge request notes

Use when the user wants a flat note stream rather than thread state.

Endpoint:

- `GET /projects/:id/merge_requests/:merge_request_iid/notes`

### Merge request pipelines

Use when the user explicitly wants MR-specific pipelines.

Endpoint:

- `GET /projects/:id/merge_requests/:merge_request_iid/pipelines`

If the user only needs the latest pipeline state, the MR detail response often already includes `head_pipeline`.

## Repository Files

These endpoints are supported in GitLab Free and are good for inspecting branch content.

### Read raw file content

Endpoint:

- `GET /projects/:id/repository/files/:file_path/raw`

Use `ref=<branch|tag|commit>` when the branch matters.

Example:

```bash
file_ref="$($helper urlencode ".gitlab-ci.yml")"

"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/repository/files/$file_ref/raw" \
  "ref=release/1.2"
```

### Read file metadata and base64 content

Endpoint:

- `GET /projects/:id/repository/files/:file_path`

Use this only when the user wants metadata such as blob IDs, size, or last commit.

### Read metadata only

Endpoint:

- `HEAD /projects/:id/repository/files/:file_path`

Useful headers:

- `X-Gitlab-Blob-Id`
- `X-Gitlab-Last-Commit-Id`
- `X-Gitlab-Ref`
- `X-Gitlab-Size`

## Pipelines

### List project pipelines

Endpoint:

- `GET /projects/:id/pipelines`

Useful filters:

- `ref=<branch>`
- `status=failed|running|success|pending|...`
- `source=<pipeline source>`
- `per_page=<n>`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/pipelines" \
  "ref=main" \
  "status=failed" \
  "per_page=5"
```

### Get the latest pipeline for a ref

Endpoint:

- `GET /projects/:id/pipelines/latest`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/pipelines/latest" \
  "ref=main"
```

### Get one pipeline

Endpoint:

- `GET /projects/:id/pipelines/:pipeline_id`

Important fields:

- `status`
- `ref`
- `sha`
- `source`
- `web_url`
- `started_at`
- `finished_at`
- `duration`
- `queued_duration`
- `yaml_errors`
- `detailed_status`

## Jobs And Logs

### List jobs in a pipeline

Endpoint:

- `GET /projects/:id/pipelines/:pipeline_id/jobs`

Useful filters:

- `scope[]=failed`
- `scope[]=running`
- `include_retried=true`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/pipelines/$pipeline_id/jobs" \
  "scope[]=failed"
```

### Get one job

Endpoint:

- `GET /projects/:id/jobs/:job_id`

Important fields:

- `name`
- `stage`
- `status`
- `failure_reason`
- `allow_failure`
- `runner`
- `web_url`
- `pipeline`

### Get job trace

Endpoint:

- `GET /projects/:id/jobs/:job_id/trace`

Example:

```bash
"$helper" --repo "$repo_root" request GET \
  "/projects/$project_ref/jobs/$job_id/trace"
```

The trace can be large. Prefer to summarize the key failing section instead of relaying the whole file.

## Practical Recipes

### Current-project issue search plus conversation

1. Search issues with `/projects/:id/issues`.
2. Fetch the chosen issue with `/projects/:id/issues/:iid`.
3. Use `/discussions` if the user wants threads.
4. Use `/notes?activity_filter=only_comments` if the user wants a flat comment stream.

### MR review state

1. Fetch MR details.
2. Fetch MR discussions.
3. Summarize:
   - `detailed_merge_status`
   - `blocking_discussions_resolved`
   - unresolved resolvable threads
   - `head_pipeline.status`

### Branch file plus CI follow-up

1. Fetch raw file content with the target `ref`.
2. Fetch the latest pipeline for that branch or list failed pipelines for that branch.
3. Fetch pipeline jobs.
4. Fetch the failed job trace if the user wants logs.

## Troubleshooting

- `401 Unauthorized`: token invalid or missing.
- `403 Forbidden`: access denied, or latest pipeline endpoint had no accessible pipeline for the ref.
- `404 Not Found`: wrong project path or IID, private resource without permission, or wrong encoded file path.
- `429 Too Many Requests`: GitLab search rate-limited the request. Reduce search volume.
- Most GitLab list endpoints default to `20` results. Add `per_page` intentionally.
- Encode project paths, group paths, and file paths before using them in API paths.
- For file contents, prefer `/raw` so you do not need to decode base64.
- For unresolved merge request comments, do not rely on Notes API alone; it does not expose per-thread resolution state.
