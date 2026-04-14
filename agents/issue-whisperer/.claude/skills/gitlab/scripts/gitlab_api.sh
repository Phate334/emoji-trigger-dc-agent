#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  gitlab_api.sh [--repo PATH] discover
  gitlab_api.sh [--repo PATH] project-path
  gitlab_api.sh [--repo PATH] project-ref [PROJECT_PATH_OR_ID]
  gitlab_api.sh urlencode VALUE
  gitlab_api.sh [--repo PATH] request GET|HEAD API_PATH [key=value ...]

Commands:
  discover     Print discovered host, API base, project path, and token source.
  project-path Print the default project path derived from origin.
  project-ref  Print a project identifier safe for GitLab API paths.
  urlencode    Percent-encode a value for GitLab API usage.
  request      Perform a read-only GitLab API request with curl or wget.

Examples:
  gitlab_api.sh --repo . discover
  gitlab_api.sh --repo . project-ref
  gitlab_api.sh urlencode '.gitlab-ci.yml'
  gitlab_api.sh --repo . request GET '/projects/group%2Fproject/issues' 'scope=all' 'search=timeout'
EOF
}

err() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

trim_whitespace() {
  local value="${1:-}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

read_dotenv_var() {
  local env_file="$1"
  local key="$2"
  local line=""
  local value=""

  [[ -f "$env_file" ]] || return 1

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue

    if [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=(.*)$ ]]; then
      value="${BASH_REMATCH[2]}"
      value="$(trim_whitespace "$value")"

      if [[ "$value" =~ ^\"(.*)\"[[:space:]]*(#.*)?$ ]]; then
        value="${BASH_REMATCH[1]}"
      elif [[ "$value" =~ ^\'(.*)\'[[:space:]]*(#.*)?$ ]]; then
        value="${BASH_REMATCH[1]}"
      else
        value="${value%%#*}"
        value="$(trim_whitespace "$value")"
      fi

      printf '%s' "$value"
      return 0
    fi
  done < "$env_file"

  return 1
}

urlencode() {
  local raw="${1:-}"
  local encoded=""
  local character=""
  local hex=""
  local index=0
  local length=0
  local LC_ALL=C

  length=${#raw}

  for ((index = 0; index < length; index++)); do
    character="${raw:index:1}"
    case "$character" in
      [a-zA-Z0-9._~-])
        encoded+="$character"
        ;;
      *)
        printf -v hex '%%%02X' "'$character"
        encoded+="$hex"
        ;;
    esac
  done

  printf '%s' "$encoded"
}

project_ref_from_value() {
  local value="${1:-}"

  [[ -n "$value" ]] || return 1

  if [[ "$value" =~ ^[0-9]+$ ]]; then
    printf '%s' "$value"
  else
    urlencode "$value"
  fi
}

resolve_repo_root() {
  local repo_hint="${1:-}"

  if [[ -n "$repo_hint" ]]; then
    [[ -d "$repo_hint" ]] || err "Repository path not found: $repo_hint"
    (
      cd "$repo_hint"
      if git rev-parse --show-toplevel >/dev/null 2>&1; then
        git rev-parse --show-toplevel
      else
        pwd
      fi
    )
    return 0
  fi

  if git rev-parse --show-toplevel >/dev/null 2>&1; then
    git rev-parse --show-toplevel
  else
    pwd
  fi
}

parse_remote_url() {
  local remote_url="$1"
  local remainder=""

  CTX_SCHEME="https"
  CTX_HOST=""
  CTX_PROJECT_PATH=""

  if [[ "$remote_url" =~ ^https?:// ]]; then
    CTX_SCHEME="${remote_url%%://*}"
    remainder="${remote_url#*://}"
    remainder="${remainder#*@}"
    CTX_HOST="${remainder%%/*}"
    CTX_PROJECT_PATH="${remainder#*/}"
  elif [[ "$remote_url" =~ ^ssh:// ]]; then
    remainder="${remote_url#ssh://}"
    remainder="${remainder#*@}"
    CTX_HOST="${remainder%%/*}"
    CTX_PROJECT_PATH="${remainder#*/}"
  elif [[ "$remote_url" =~ ^[^@]+@[^:]+:.+$ ]]; then
    remainder="${remote_url#*@}"
    CTX_HOST="${remainder%%:*}"
    CTX_PROJECT_PATH="${remainder#*:}"
  else
    return 1
  fi

  CTX_PROJECT_PATH="${CTX_PROJECT_PATH%.git}"
  CTX_PROJECT_PATH="${CTX_PROJECT_PATH#/}"
  CTX_HOST_SOURCE="origin"
  CTX_PROJECT_SOURCE="origin"
  return 0
}

host_looks_like_non_gitlab() {
  local host="${1,,}"

  case "$host" in
    github.com|www.github.com|api.github.com|*.github.com)
      return 0
      ;;
  esac

  [[ "$host" == *github* ]]
}

discover_context() {
  local repo_hint="${1:-}"
  local require_token="${2:-1}"
  local token_from_env=""
  local host_from_dotenv=""
  local project_path_from_dotenv=""
  local configured_host=""
  local configured_host_source=""
  local configured_project_path=""
  local configured_project_source=""

  CTX_REPO_ROOT="$(resolve_repo_root "$repo_hint")"
  CTX_REMOTE_URL=""
  CTX_TOKEN=""
  CTX_TOKEN_SOURCE=""
  CTX_HOST=""
  CTX_HOST_SOURCE=""
  CTX_PROJECT_PATH=""
  CTX_PROJECT_SOURCE=""
  CTX_PROJECT_REF=""
  CTX_SCHEME="https"
  CTX_API_BASE=""

  if git -C "$CTX_REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    CTX_REMOTE_URL="$(git -C "$CTX_REPO_ROOT" remote get-url origin 2>/dev/null || true)"
  fi

  if [[ -n "$CTX_REMOTE_URL" ]]; then
    parse_remote_url "$CTX_REMOTE_URL" || true
  fi

  if host_from_dotenv="$(read_dotenv_var "$CTX_REPO_ROOT/.env" GITLAB_HOST 2>/dev/null)"; then
    configured_host="$host_from_dotenv"
    configured_host_source="$CTX_REPO_ROOT/.env"
  elif [[ -n "${GITLAB_HOST:-}" ]]; then
    configured_host="$GITLAB_HOST"
    configured_host_source="environment"
  fi

  if project_path_from_dotenv="$(read_dotenv_var "$CTX_REPO_ROOT/.env" GITLAB_PROJECT_PATH 2>/dev/null)"; then
    configured_project_path="$project_path_from_dotenv"
    configured_project_source="$CTX_REPO_ROOT/.env"
  elif [[ -n "${GITLAB_PROJECT_PATH:-}" ]]; then
    configured_project_path="$GITLAB_PROJECT_PATH"
    configured_project_source="environment"
  fi

  if [[ -n "$configured_host" && -n "$CTX_HOST" ]] && host_looks_like_non_gitlab "$CTX_HOST"; then
    CTX_HOST="$configured_host"
    CTX_HOST_SOURCE="$configured_host_source"
    if [[ "$CTX_PROJECT_SOURCE" == "origin" ]]; then
      CTX_PROJECT_PATH=""
      CTX_PROJECT_SOURCE=""
    fi
  fi

  if [[ -z "$CTX_HOST" && -n "$configured_host" ]]; then
    CTX_HOST="$configured_host"
    CTX_HOST_SOURCE="$configured_host_source"
  fi

  if [[ -z "$CTX_PROJECT_PATH" && -n "$configured_project_path" ]]; then
    CTX_PROJECT_PATH="$configured_project_path"
    CTX_PROJECT_SOURCE="$configured_project_source"
  fi

  if token_from_env="$(read_dotenv_var "$CTX_REPO_ROOT/.env" GITLAB_TOKEN 2>/dev/null)"; then
    CTX_TOKEN="$token_from_env"
    CTX_TOKEN_SOURCE="$CTX_REPO_ROOT/.env"
  elif [[ -n "${GITLAB_TOKEN:-}" ]]; then
    CTX_TOKEN="$GITLAB_TOKEN"
    CTX_TOKEN_SOURCE="environment"
  fi

  if [[ -n "$CTX_HOST" ]]; then
    CTX_API_BASE="${CTX_SCHEME}://$CTX_HOST/api/v4"
  fi

  if [[ -n "$CTX_PROJECT_PATH" ]]; then
    CTX_PROJECT_REF="$(project_ref_from_value "$CTX_PROJECT_PATH")"
  fi

  if [[ -z "$CTX_HOST" ]]; then
    err "Could not determine GITLAB_HOST from git remote origin or environment."
  fi

  if [[ "$require_token" == "1" && -z "$CTX_TOKEN" ]]; then
    err "Could not find GITLAB_TOKEN in $CTX_REPO_ROOT/.env or the environment."
  fi
}

build_url() {
  local endpoint="$1"
  shift || true
  local query_args=("$@")
  local separator='?'
  local url=''
  local arg=''
  local key=''
  local value=''

  case "$endpoint" in
    http://*|https://*)
      url="$endpoint"
      ;;
    /api/v4/*)
      url="${CTX_SCHEME}://$CTX_HOST$endpoint"
      ;;
    /*)
      url="$CTX_API_BASE$endpoint"
      ;;
    *)
      url="$CTX_API_BASE/$endpoint"
      ;;
  esac

  if [[ "$url" == *\?* ]]; then
    separator='&'
  fi

  for arg in "${query_args[@]}"; do
    [[ "$arg" == *=* ]] || err "Query arguments must use key=value form: $arg"
    key="${arg%%=*}"
    value="${arg#*=}"
    url+="$separator$(urlencode "$key")=$(urlencode "$value")"
    separator='&'
  done

  printf '%s' "$url"
}

run_http_request() {
  local method="$1"
  local url="$2"

  if command -v curl >/dev/null 2>&1; then
    curl \
      --silent \
      --show-error \
      --fail \
      --location \
      --request "$method" \
      --header "PRIVATE-TOKEN: $CTX_TOKEN" \
      "$url"
    return 0
  fi

  if command -v wget >/dev/null 2>&1; then
    if [[ "$method" == "HEAD" ]]; then
      wget \
        --server-response \
        --spider \
        --header="PRIVATE-TOKEN: $CTX_TOKEN" \
        "$url" 2>&1
    else
      wget \
        --quiet \
        --output-document=- \
        --header="PRIVATE-TOKEN: $CTX_TOKEN" \
        "$url"
    fi
    return 0
  fi

  err "Neither curl nor wget is available."
}

cmd_discover() {
  discover_context "$REPO_HINT" 0
  cat <<EOF
repo_root=$CTX_REPO_ROOT
token_source=${CTX_TOKEN_SOURCE:-missing}
host_source=${CTX_HOST_SOURCE:-missing}
project_source=${CTX_PROJECT_SOURCE:-missing}
scheme=$CTX_SCHEME
host=$CTX_HOST
api_base=$CTX_API_BASE
project_path=${CTX_PROJECT_PATH:-}
project_ref=${CTX_PROJECT_REF:-}
remote_url=${CTX_REMOTE_URL:-}
EOF
}

cmd_project_path() {
  discover_context "$REPO_HINT" 0
  [[ -n "$CTX_PROJECT_PATH" ]] || err "Could not determine project path from origin or environment."
  printf '%s\n' "$CTX_PROJECT_PATH"
}

cmd_project_ref() {
  local explicit_project="${1:-}"

  discover_context "$REPO_HINT" 0

  if [[ -n "$explicit_project" ]]; then
    project_ref_from_value "$explicit_project"
    printf '\n'
    return 0
  fi

  [[ -n "$CTX_PROJECT_REF" ]] || err "Could not determine project path from origin or environment."
  printf '%s\n' "$CTX_PROJECT_REF"
}

cmd_request() {
  local method="${1:-}"
  local endpoint="${2:-}"
  shift 2 || true

  [[ -n "$method" ]] || err "Missing HTTP method."
  [[ -n "$endpoint" ]] || err "Missing API path."

  case "$method" in
    GET|HEAD)
      ;;
    *)
      err "Only GET and HEAD are allowed in this helper."
      ;;
  esac

  discover_context "$REPO_HINT" 1
  run_http_request "$method" "$(build_url "$endpoint" "$@")"
}

REPO_HINT=''

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      [[ $# -ge 2 ]] || err "--repo requires a path."
      REPO_HINT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
  discover)
    cmd_discover "$@"
    ;;
  project-path)
    cmd_project_path "$@"
    ;;
  project-ref)
    cmd_project_ref "$@"
    ;;
  urlencode)
    [[ $# -ge 1 ]] || err "urlencode requires a value."
    urlencode "$1"
    printf '\n'
    ;;
  request)
    cmd_request "$@"
    ;;
  '' )
    usage
    exit 1
    ;;
  *)
    err "Unknown command: $COMMAND"
    ;;
esac
