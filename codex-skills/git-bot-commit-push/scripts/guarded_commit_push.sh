#!/bin/sh
set -eu

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <repo> <commit-message>" >&2
  exit 2
fi

repo=$1
message=$2

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"$script_dir/configure_git_bot.sh" "$repo" >/dev/null

remote_url=$(git -C "$repo" remote get-url origin)
branch=$(git -C "$repo" branch --show-current)

python3 - "$remote_url" "${CODEX_GIT_ALLOWED_HOSTS:-github.com}" "${CODEX_GIT_ALLOWED_ORGS:-}" <<'PY'
import sys
from urllib.parse import urlparse

remote = sys.argv[1]
allowed_hosts = {x.strip() for x in sys.argv[2].split(",") if x.strip()}
allowed_orgs = {x.strip() for x in sys.argv[3].split(",") if x.strip()}

host = ""
org = ""
if "@" in remote and ":" in remote and not remote.startswith("http"):
    after_at = remote.split("@", 1)[1]
    host, path = after_at.split(":", 1)
    org = path.split("/", 1)[0]
else:
    parsed = urlparse(remote)
    host = parsed.hostname or ""
    path = (parsed.path or "").lstrip("/")
    org = path.split("/", 1)[0] if path else ""

if allowed_hosts and host not in allowed_hosts:
    raise SystemExit(f"remote host '{host}' not in allowlist")
if allowed_orgs and org not in allowed_orgs:
    raise SystemExit(f"remote org '{org}' not in allowlist")
PY

if ! git -C "$repo" diff --cached --quiet; then
  :
else
  echo "no staged changes; stage files explicitly before running this script" >&2
  exit 1
fi

if [ -n "${CODEX_GIT_TEST_COMMAND:-}" ]; then
  (cd "$repo" && /bin/sh -lc "$CODEX_GIT_TEST_COMMAND")
fi

if [ -n "${CODEX_GIT_PUSH_URL:-}" ]; then
  push_target=$CODEX_GIT_PUSH_URL
elif [ "${CODEX_GIT_ALLOW_EXISTING_ORIGIN:-0}" = "1" ]; then
  push_target=origin
else
  echo "missing bot push target; set CODEX_GIT_PUSH_URL or explicitly allow existing origin" >&2
  exit 1
fi

git -C "$repo" commit -m "$message"
git -C "$repo" push "$push_target" "HEAD:$branch"
